"""
Main orchestrator for the Proxmox installation workflow.
"""

from datetime import datetime
from typing import Optional

from ..auth.manager import OpenStackAuthManager
from ..cleanup.manager import CleanupManager
from ..exceptions import (
    BuildError,
    ConfigurationError,
    GPUPassthroughError,
    ProxmoxAutomationError,
)
from ..gpu.detector import GPUDetector
from ..gpu.iommu import IOMMUConfigurator
from ..gpu.vfio import VFIOManager
from ..logging_config import get_logger
from ..models import BuildConfiguration, BuildState, BuildStatus
from ..provisioner.instance import InstanceProvisioner
from ..provisioner.ssh import SSHConnection
from ..proxmox.installer import ProxmoxInstaller
from ..proxmox.network import NetworkConfigurator
from ..proxmox.storage import StorageConfigurator
from ..vm.creator import VMCreator
from ..vm.validator import VMValidator

logger = get_logger("orchestrator.builder")


class ProxmoxBuilder:
    """Orchestrates the complete Proxmox installation workflow."""

    def __init__(self) -> None:
        self._cleanup = CleanupManager()

    def validate_config(self, config: BuildConfiguration) -> bool:
        """
        Validate the build configuration.

        Args:
            config: Build configuration to validate.

        Returns:
            True if configuration is valid.

        Raises:
            ConfigurationError: If configuration is invalid.
        """
        errors = []

        # Validate credentials
        if not config.credentials.auth_url:
            errors.append("openstack.auth_url is required")
        if not config.credentials.region:
            errors.append("openstack.region is required")
        if config.credentials.auth_type == "v3applicationcredential":
            if not config.credentials.application_credential_id:
                errors.append("openstack.application_credential_id is required")
            if not config.credentials.application_credential_secret:
                errors.append("openstack.application_credential_secret is required")

        # Validate instance spec
        if not config.instance_spec.base_image_name:
            errors.append("instance.base_image_name is required")
        if not config.instance_spec.flavor_name:
            errors.append("instance.flavor_name is required")
        if not config.instance_spec.ssh_key_name:
            errors.append("instance.ssh_key_name is required")

        if errors:
            error_msg = "; ".join(errors)
            raise ConfigurationError(f"Configuration validation failed: {error_msg}")

        logger.info("Configuration validation passed")
        return True

    def run(self, config: BuildConfiguration) -> BuildState:
        """
        Execute the complete Proxmox installation workflow.

        Steps:
        1. Authenticate to OpenStack
        2. Create baremetal instance
        3. Wait for instance to be ready
        4. Connect via SSH
        5. Install Proxmox VE
        6. Reboot into Proxmox kernel
        7. Configure GPU passthrough (if enabled)
        8. Create test VM with GPU (if enabled)
        9. Validate

        Args:
            config: Build configuration.

        Returns:
            BuildState with final status.
        """
        state = BuildState(started_at=datetime.utcnow())
        ssh = SSHConnection()

        try:
            # Validate configuration
            self.validate_config(config)

            # Step 1: Authenticate
            state.status = BuildStatus.PROVISIONING
            state.add_log("Authenticating to OpenStack...")
            auth_manager = OpenStackAuthManager()
            connection = auth_manager.authenticate(config.credentials)

            # Step 2: Create instance
            state.add_log("Creating baremetal instance...")
            provisioner = InstanceProvisioner(connection)
            instance = provisioner.create_instance(config.instance_spec)
            state.instance = instance
            self._cleanup.register_instance(provisioner, instance)

            # Step 3: Wait for ready
            state.add_log("Waiting for instance to be ready...")
            provisioner.wait_for_ready(
                instance, timeout=config.timeouts["instance_ready"]
            )

            # Step 4: Connect via SSH
            state.add_log("Establishing SSH connection...")
            host_ip = provisioner.get_instance_ip(instance)
            ssh.connect(
                host=host_ip,
                username=config.instance_spec.ssh_username,
                key_path=config.instance_spec.ssh_key_path,
                timeout=config.timeouts["ssh_connection"],
            )

            # Step 5: Install Proxmox
            state.status = BuildStatus.INSTALLING_PROXMOX
            state.add_log("Installing Proxmox VE...")
            pve_installer = ProxmoxInstaller(config.proxmox)
            pve_installer.install(ssh)

            # Configure network
            state.add_log("Configuring network bridge...")
            network_config = NetworkConfigurator()
            network_config.configure_bridge(ssh, config.proxmox.network_bridge)

            # Step 6: Reboot into Proxmox kernel
            if config.gpu_passthrough.enabled:
                # Configure IOMMU before reboot
                state.status = BuildStatus.CONFIGURING_GPU
                state.add_log("Configuring IOMMU for GPU passthrough...")
                iommu_config = IOMMUConfigurator()
                iommu_config.configure(ssh, config.gpu_passthrough.iommu_type)

                # Configure VFIO blacklist (before reboot)
                state.add_log("Configuring VFIO driver binding...")
                vfio_manager = VFIOManager()

                # Detect GPUs before reboot to get device IDs
                gpu_detector = GPUDetector()
                gpu_devices = gpu_detector.detect(ssh)
                state.gpu_devices = gpu_devices

                if gpu_devices:
                    vfio_manager.bind_devices(
                        ssh, gpu_devices, config.gpu_passthrough.blacklist_drivers
                    )
                else:
                    state.add_log("WARNING: No GPU devices detected")

            # Reboot
            state.add_log("Rebooting into Proxmox kernel...")
            pve_installer.reboot_and_reconnect(
                ssh,
                host=host_ip,
                username="root",  # After Proxmox install, connect as root
                key_path=config.instance_spec.ssh_key_path,
                timeout=config.timeouts["reboot_wait"],
            )

            # Verify Proxmox installation
            state.add_log("Verifying Proxmox VE installation...")
            if not pve_installer.verify_installation(ssh):
                raise BuildError("Proxmox VE verification failed after reboot")

            # Configure storage
            storage_config = StorageConfigurator()
            storage_config.configure(ssh, config.proxmox.storage_type)

            # Set Proxmox URL
            state.proxmox_url = f"https://{host_ip}:8006"

            # Step 7: Verify GPU passthrough
            if config.gpu_passthrough.enabled and state.gpu_devices:
                state.add_log("Verifying GPU passthrough configuration...")
                iommu_config = IOMMUConfigurator()
                if not iommu_config.verify(ssh):
                    state.add_log("WARNING: IOMMU verification failed")

                vfio_manager = VFIOManager()
                if not vfio_manager.verify_binding(ssh, state.gpu_devices):
                    state.add_log("WARNING: Not all GPUs bound to VFIO")

            # Step 8: Create test VM
            if config.test_vm.enabled:
                state.status = BuildStatus.CREATING_VM
                state.add_log("Creating test VM with GPU passthrough...")
                vm_creator = VMCreator()
                gpu_for_vm = state.gpu_devices[0] if state.gpu_devices else None
                test_vm = vm_creator.create(ssh, config.test_vm, gpu=gpu_for_vm)
                state.test_vm = test_vm

                # Start the VM
                if test_vm.gpu_attached:
                    state.add_log("Starting test VM...")
                    vm_creator.start(ssh, test_vm.vmid)

                    # Validate
                    state.status = BuildStatus.VALIDATING
                    validator = VMValidator()
                    if validator.validate_gpu_visible(ssh, test_vm.vmid):
                        state.add_log("✓ GPU passthrough validated successfully")
                    else:
                        state.add_log("⚠ GPU visibility could not be fully confirmed")

            # Done!
            state.status = BuildStatus.COMPLETED
            state.completed_at = datetime.utcnow()
            state.add_log("Build completed successfully!")

            logger.info("Proxmox installation completed successfully")
            logger.info("Web UI: %s", state.proxmox_url)
            if pve_installer.root_password:
                logger.info("Root password: %s", pve_installer.root_password)

        except ProxmoxAutomationError as e:
            state.status = BuildStatus.FAILED
            state.error_message = str(e)
            state.completed_at = datetime.utcnow()
            state.add_log(f"ERROR: {e}")
            logger.error("Build failed: %s", e)

        except Exception as e:
            state.status = BuildStatus.FAILED
            state.error_message = f"Unexpected error: {e}"
            state.completed_at = datetime.utcnow()
            state.add_log(f"UNEXPECTED ERROR: {e}")
            logger.exception("Unexpected error during build")

        finally:
            ssh.disconnect()

        return state

    def cleanup(self, state: BuildState) -> bool:
        """
        Clean up all resources created during the build.

        Args:
            state: Build state with resource references.

        Returns:
            True if cleanup succeeds.
        """
        return self._cleanup.cleanup_all()
