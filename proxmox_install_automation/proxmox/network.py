"""
Network configuration for Proxmox VE.
"""

from ..exceptions import NetworkConfigError
from ..logging_config import get_logger
from ..provisioner.ssh import SSHConnection

logger = get_logger("proxmox.network")


class NetworkConfigurator:
    """Configures network bridges for Proxmox VE."""

    def configure_bridge(
        self, ssh: SSHConnection, bridge_name: str = "vmbr0"
    ) -> bool:
        """
        Configure a network bridge for VM connectivity.

        Args:
            ssh: Active SSH connection.
            bridge_name: Name of the bridge interface.

        Returns:
            True if configuration succeeds.

        Raises:
            NetworkConfigError: If configuration fails.
        """
        logger.info("Configuring network bridge: %s", bridge_name)

        try:
            # Detect the primary network interface
            result = ssh.execute_sudo(
                "ip route | grep default | awk '{print $5}' | head -1"
            )
            primary_iface = result.stdout.strip()
            if not primary_iface:
                raise NetworkConfigError("Could not detect primary network interface")

            logger.info("Primary network interface: %s", primary_iface)

            # Get current IP configuration
            result = ssh.execute_sudo(
                f"ip -4 addr show {primary_iface} | grep inet | awk '{{print $2}}'"
            )
            ip_cidr = result.stdout.strip()

            result = ssh.execute_sudo(
                "ip route | grep default | awk '{print $3}'"
            )
            gateway = result.stdout.strip()

            if not ip_cidr or not gateway:
                raise NetworkConfigError("Could not determine IP configuration")

            # Create the bridge configuration
            interfaces_config = f"""# Network configuration for Proxmox VE
auto lo
iface lo inet loopback

auto {primary_iface}
iface {primary_iface} inet manual

auto {bridge_name}
iface {bridge_name} inet static
    address {ip_cidr}
    gateway {gateway}
    bridge-ports {primary_iface}
    bridge-stp off
    bridge-fd 0
"""
            # Write the configuration
            ssh.execute_sudo(
                f"bash -c 'cat > /etc/network/interfaces << \"EOF\"\n{interfaces_config}EOF'"
            )

            logger.info("Network bridge '%s' configured successfully", bridge_name)
            return True

        except NetworkConfigError:
            raise
        except Exception as e:
            raise NetworkConfigError(f"Network configuration failed: {e}") from e

    def verify_bridge(self, ssh: SSHConnection, bridge_name: str = "vmbr0") -> bool:
        """
        Verify the network bridge is operational.

        Args:
            ssh: Active SSH connection.
            bridge_name: Bridge name to verify.

        Returns:
            True if bridge is up and operational.
        """
        result = ssh.execute_sudo(f"ip link show {bridge_name}")
        if result.exit_code != 0:
            logger.warning("Bridge %s not found", bridge_name)
            return False

        if "UP" in result.stdout:
            logger.info("Bridge %s is UP", bridge_name)
            return True

        logger.warning("Bridge %s exists but is not UP", bridge_name)
        return False
