"""
Proxmox VE installer - handles package installation and base configuration.
"""

import secrets
import string
from typing import Optional

from ..exceptions import ProxmoxInstallError
from ..logging_config import get_logger
from ..models import ProxmoxConfig
from ..provisioner.ssh import SSHConnection

logger = get_logger("proxmox.installer")


class ProxmoxInstaller:
    """Handles Proxmox VE installation on a Debian system."""

    def __init__(self, config: ProxmoxConfig) -> None:
        self._config = config
        self._root_password: Optional[str] = None

    @property
    def root_password(self) -> str:
        """Get the configured or generated root password."""
        if self._root_password is None:
            if self._config.root_password:
                self._root_password = self._config.root_password
            else:
                # Generate a secure random password
                alphabet = string.ascii_letters + string.digits + "!@#$%"
                self._root_password = "".join(
                    secrets.choice(alphabet) for _ in range(20)
                )
        return self._root_password

    def install(self, ssh: SSHConnection) -> bool:
        """
        Install Proxmox VE on the remote system.

        Args:
            ssh: Active SSH connection.

        Returns:
            True if installation succeeds.

        Raises:
            ProxmoxInstallError: If installation fails.
        """
        logger.info("Starting Proxmox VE %s installation", self._config.version)

        try:
            # Step 1: Configure hostname
            self._configure_hostname(ssh)

            # Step 2: Add Proxmox repository
            self._add_proxmox_repo(ssh)

            # Step 3: Install Proxmox packages
            self._install_packages(ssh)

            # Step 4: Set root password
            self._set_root_password(ssh)

            # Step 5: Remove OS kernel (optional, use Proxmox kernel)
            self._configure_kernel(ssh)

            logger.info("Proxmox VE installation completed")
            return True

        except Exception as e:
            raise ProxmoxInstallError(
                f"Proxmox VE installation failed: {e}"
            ) from e

    def _configure_hostname(self, ssh: SSHConnection) -> None:
        """Configure the hostname for Proxmox."""
        logger.info("Configuring hostname")

        # Get current IP
        result = ssh.execute_sudo(
            "hostname -I | awk '{print $1}'"
        )
        ip_address = result.stdout.strip()

        # Set hostname
        hostname = "proxmox"
        ssh.execute_sudo(f"hostnamectl set-hostname {hostname}")

        # Configure /etc/hosts
        hosts_content = (
            f"127.0.0.1 localhost\n"
            f"{ip_address} {hostname}.local {hostname}\n"
        )
        ssh.execute_sudo(
            f"bash -c 'echo \"{hosts_content}\" > /etc/hosts'"
        )

    def _add_proxmox_repo(self, ssh: SSHConnection) -> None:
        """Add Proxmox VE APT repository."""
        logger.info("Adding Proxmox VE repository")

        # Add Proxmox GPG key
        ssh.execute_sudo(
            "wget -qO /etc/apt/trusted.gpg.d/proxmox-release-bookworm.gpg "
            "http://download.proxmox.com/debian/proxmox-release-bookworm.gpg"
        )

        # Add repository
        if self._config.enterprise_repo:
            repo_line = (
                "deb https://enterprise.proxmox.com/debian/pve bookworm pve-enterprise"
            )
        else:
            repo_line = (
                "deb http://download.proxmox.com/debian/pve bookworm pve-no-subscription"
            )

        ssh.execute_sudo(
            f"bash -c 'echo \"{repo_line}\" > /etc/apt/sources.list.d/pve-install-repo.list'"
        )

        # Update package lists
        result = ssh.execute_sudo("apt-get update", timeout=300)
        if result.exit_code != 0:
            raise ProxmoxInstallError(f"apt-get update failed: {result.stderr}")

    def _install_packages(self, ssh: SSHConnection) -> None:
        """Install Proxmox VE packages."""
        logger.info("Installing Proxmox VE packages (this may take several minutes)")

        # Set non-interactive frontend
        env = "DEBIAN_FRONTEND=noninteractive"

        # Install Proxmox VE
        result = ssh.execute_sudo(
            f"{env} apt-get install -y proxmox-ve postfix open-iscsi chrony",
            timeout=1200,
        )
        if result.exit_code != 0:
            raise ProxmoxInstallError(
                f"Failed to install Proxmox packages: {result.stderr}"
            )

        logger.info("Proxmox VE packages installed successfully")

    def _set_root_password(self, ssh: SSHConnection) -> None:
        """Set the root password for Proxmox web UI access."""
        logger.info("Setting root password for Proxmox")
        password = self.root_password
        ssh.execute_sudo(
            f"bash -c 'echo \"root:{password}\" | chpasswd'"
        )

    def _configure_kernel(self, ssh: SSHConnection) -> None:
        """Configure kernel settings for Proxmox."""
        logger.info("Configuring kernel for Proxmox VE")

        # Remove the Debian default kernel (optional)
        # Keep Proxmox kernel as the boot kernel
        ssh.execute_sudo(
            "apt-get remove -y linux-image-amd64 'linux-image-6.1*' || true",
            timeout=120,
        )

        # Update GRUB
        ssh.execute_sudo("update-grub", timeout=60)

    def verify_installation(self, ssh: SSHConnection) -> bool:
        """
        Verify Proxmox VE is installed and running.

        Args:
            ssh: Active SSH connection.

        Returns:
            True if Proxmox is running correctly.
        """
        logger.info("Verifying Proxmox VE installation")

        # Check pveversion
        result = ssh.execute_sudo("pveversion")
        if result.exit_code != 0:
            logger.error("pveversion command failed")
            return False

        logger.info("Proxmox version: %s", result.stdout.strip())

        # Check pve-cluster service
        result = ssh.execute_sudo("systemctl is-active pve-cluster")
        if result.stdout.strip() != "active":
            logger.error("pve-cluster service is not active")
            return False

        # Check pvedaemon service
        result = ssh.execute_sudo("systemctl is-active pvedaemon")
        if result.stdout.strip() != "active":
            logger.error("pvedaemon service is not active")
            return False

        # Check pveproxy (web UI)
        result = ssh.execute_sudo("systemctl is-active pveproxy")
        if result.stdout.strip() != "active":
            logger.error("pveproxy service is not active")
            return False

        logger.info("Proxmox VE is installed and all services are running")
        return True

    def reboot_and_reconnect(
        self,
        ssh: SSHConnection,
        host: str,
        username: str,
        key_path: str,
        timeout: int = 300,
    ) -> None:
        """
        Reboot the instance and re-establish SSH connection.

        Args:
            ssh: Current SSH connection.
            host: Host to reconnect to.
            username: SSH username.
            key_path: SSH key path.
            timeout: Reconnection timeout.
        """
        logger.info("Rebooting instance for Proxmox kernel...")
        ssh.execute_sudo("reboot")
        ssh.disconnect()

        # Wait before attempting to reconnect
        import time
        time.sleep(30)

        # Reconnect
        ssh.connect(host, username, key_path, timeout=timeout)
        logger.info("Reconnected after reboot")
