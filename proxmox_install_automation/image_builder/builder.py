"""
ImageBuilder orchestrator for the qcow2 image building pipeline.

Sequences all pipeline steps: validate → auth → create instance → wait →
SSH → disk space check → download ISO → verify → convert → verify →
snapshot → wait → upload → wait → cleanup.

Uses try/finally to ensure cleanup runs on any failure.
"""

import time
from datetime import datetime, timezone
from typing import List

from ..logging_config import get_logger
from ..provisioner.ssh import SSHConnection
from .auth import ImageBuildAuthManager
from .cleanup import ImageBuildCleanupManager
from .config_validator import ImageBuildConfigValidator
from .exceptions import ConfigurationError, ImageBuildError
from .glance_uploader import GlanceUploader
from .instance import ImageBuildInstanceManager
from .iso_converter import ISOConverter
from .iso_downloader import ISODownloader
from .models import (
    CleanupResource,
    ImageBuildConfig,
    ImageBuildResult,
    ImageMetadata,
)
from .snapshot import SnapshotManager, generate_snapshot_name

logger = get_logger("image_builder.builder")


class ImageBuilder:
    """Orchestrates the complete qcow2 image build pipeline."""

    def build(self, config: ImageBuildConfig) -> ImageBuildResult:
        """
        Execute the full image build pipeline.

        Steps executed in order:
        1. Validate configuration
        2. Authenticate and verify service endpoints
        3. Create Base Instance
        4. Wait for ACTIVE status
        5. Establish SSH connection
        6. Check disk space on instance
        7. Download ISO via SSH
        8. Verify ISO integrity (if iso_expected_size is set)
        9. Convert ISO to qcow2
        10. Verify qcow2 output file
        11. Create server snapshot
        12. Wait for snapshot ACTIVE
        13. Upload qcow2 to Glance with metadata
        14. Wait for image ACTIVE
        15. Cleanup (reverse order: snapshot → instance → floating IP)

        Args:
            config: Complete image build configuration.

        Returns:
            ImageBuildResult with image_id, image_name, and build_duration_seconds.

        Raises:
            ConfigurationError: If configuration validation fails.
            ImageBuildError: If any pipeline step fails.
        """
        build_start_time = datetime.now(timezone.utc)
        start_seconds = time.time()

        resources: List[CleanupResource] = []
        ssh = SSHConnection()
        connection = None

        try:
            # Step 1: Validate configuration
            logger.info("Step 1: Validating configuration")
            self.validate_config(config)

            # Step 2: Authenticate and verify service endpoints
            logger.info("Step 2: Authenticating to OpenStack")
            auth_manager = ImageBuildAuthManager()
            connection = auth_manager.authenticate(config.credentials)

            # Step 3: Create Base Instance
            logger.info("Step 3: Creating base instance")
            instance_manager = ImageBuildInstanceManager(connection)
            instance = instance_manager.create_instance(
                image_name=config.base_image_name,
                flavor_name=config.flavor_name,
                network_name=config.network_name,
                ssh_key_name=config.ssh_key_name,
            )
            resources.append(
                CleanupResource(
                    resource_type="instance",
                    resource_id=instance["id"],
                    resource_name=instance["name"],
                )
            )

            # Step 4: Wait for ACTIVE status
            logger.info("Step 4: Waiting for instance ACTIVE status")
            active_instance = instance_manager.wait_for_active(
                server_id=instance["id"],
                server_name=instance["name"],
                timeout=config.build_timeout,
            )

            # Extract IP address from instance addresses
            host_ip = self._extract_ip(active_instance)

            # Step 5: Establish SSH connection
            logger.info("Step 5: Establishing SSH connection to %s", host_ip)
            ssh.connect(
                host=host_ip,
                username="root",
                key_path=config.ssh_key_path,
            )

            # Step 6: Check disk space on instance
            logger.info("Step 6: Checking disk space")
            iso_downloader = ISODownloader()
            if config.iso_expected_size:
                iso_downloader.check_disk_space(
                    ssh=ssh,
                    directory=config.iso_download_dir,
                    required_bytes=config.iso_expected_size,
                )

            # Step 7: Download ISO via SSH
            logger.info("Step 7: Downloading ISO")
            iso_path = iso_downloader.download(
                ssh=ssh,
                url=config.iso_url,
                dest_dir=config.iso_download_dir,
                timeout=config.iso_download_timeout,
            )

            # Step 8: Verify ISO integrity (only if iso_expected_size is set)
            if config.iso_expected_size:
                logger.info("Step 8: Verifying ISO integrity")
                iso_downloader.verify_integrity(
                    ssh=ssh,
                    file_path=iso_path,
                    expected_size=config.iso_expected_size,
                )
            else:
                logger.info("Step 8: Skipping ISO integrity check (no expected size configured)")

            # Step 9: Convert ISO to qcow2
            logger.info("Step 9: Converting ISO to qcow2")
            iso_converter = ISOConverter()
            qcow2_path = iso_path.rsplit(".", 1)[0] + ".qcow2"
            iso_converter.convert(
                ssh=ssh,
                iso_path=iso_path,
                qcow2_path=qcow2_path,
                timeout=config.conversion_timeout,
            )

            # Step 10: Verify qcow2 output file
            logger.info("Step 10: Verifying qcow2 output")
            iso_converter.verify_output(ssh=ssh, qcow2_path=qcow2_path)

            # Step 11: Create server snapshot
            logger.info("Step 11: Creating server snapshot")
            snapshot_manager = SnapshotManager()
            snapshot_name = generate_snapshot_name(
                version=config.proxmox_version,
                build_start_time=build_start_time,
            )
            snapshot_id = snapshot_manager.create_snapshot(
                connection=connection,
                server_id=instance["id"],
                name=snapshot_name,
            )
            resources.append(
                CleanupResource(
                    resource_type="snapshot",
                    resource_id=snapshot_id,
                    resource_name=snapshot_name,
                )
            )

            # Step 12: Wait for snapshot ACTIVE
            logger.info("Step 12: Waiting for snapshot ACTIVE status")
            snapshot_manager.wait_for_active(
                connection=connection,
                image_id=snapshot_id,
                timeout=config.snapshot_timeout,
            )

            # Step 13: Upload qcow2 to Glance with metadata
            logger.info("Step 13: Uploading qcow2 to Glance")
            glance_uploader = GlanceUploader()
            metadata = ImageMetadata(
                name=config.target_image_name,
                disk_format="qcow2",
                container_format="bare",
                proxmox_version=config.proxmox_version,
                build_timestamp=build_start_time.isoformat(),
                visibility=config.target_visibility,
            )

            # Read the qcow2 file from the remote instance
            image_data = self._read_remote_file(ssh, qcow2_path)

            image_id = glance_uploader.upload(
                connection=connection,
                image_data=image_data,
                metadata=metadata,
            )

            # Step 14: Wait for image ACTIVE
            logger.info("Step 14: Waiting for Glance image ACTIVE status")
            glance_uploader.wait_for_active(
                connection=connection,
                image_id=image_id,
                timeout=config.build_timeout,
            )

            # Build succeeded
            build_duration = time.time() - start_seconds
            logger.info(
                "Image build completed successfully in %.1f seconds. "
                "Image ID: %s, Name: %s",
                build_duration,
                image_id,
                config.target_image_name,
            )

            return ImageBuildResult(
                image_id=image_id,
                image_name=config.target_image_name,
                build_duration_seconds=build_duration,
                snapshot_id=snapshot_id,
            )

        except ConfigurationError:
            raise
        except Exception as e:
            if not isinstance(e, ImageBuildError):
                raise ImageBuildError(
                    f"Image build pipeline failed: {e}"
                ) from e
            raise

        finally:
            # Step 15: Cleanup (always runs)
            logger.info("Step 15: Cleaning up resources")
            ssh.disconnect()

            if connection and resources:
                cleanup_manager = ImageBuildCleanupManager(connection)
                cleanup_report = cleanup_manager.cleanup(resources)
                if cleanup_report.failed > 0:
                    logger.warning(
                        "Cleanup completed with %d failure(s): %s",
                        cleanup_report.failed,
                        cleanup_report.failures,
                    )

    def validate_config(self, config: ImageBuildConfig) -> bool:
        """
        Validate configuration without executing the build.

        Args:
            config: Image build configuration to validate.

        Returns:
            True if the configuration is valid.

        Raises:
            ConfigurationError: If the configuration is invalid.
        """
        validator = ImageBuildConfigValidator()
        validator.validate(config)
        logger.info("Configuration validation passed")
        return True

    def _extract_ip(self, instance_info: dict) -> str:
        """
        Extract the first available IP address from instance addresses.

        Args:
            instance_info: Dict with 'addresses' key containing network info.

        Returns:
            The first IP address found.

        Raises:
            ImageBuildError: If no IP address is found.
        """
        addresses = instance_info.get("addresses", {})
        for network_name, addr_list in addresses.items():
            if isinstance(addr_list, list):
                for addr in addr_list:
                    if isinstance(addr, dict) and "addr" in addr:
                        return addr["addr"]
                    elif isinstance(addr, str):
                        return addr
            elif isinstance(addr_list, str):
                return addr_list

        raise ImageBuildError(
            f"No IP address found for instance '{instance_info.get('name', 'unknown')}'. "
            f"Available addresses: {addresses}"
        )

    def _read_remote_file(self, ssh: SSHConnection, remote_path: str) -> bytes:
        """
        Read a file from the remote instance via SSH.

        Uses base64 encoding to safely transfer binary data over SSH.

        Args:
            ssh: Active SSH connection.
            remote_path: Path to the file on the remote instance.

        Returns:
            Raw bytes of the file content.

        Raises:
            ImageBuildError: If the file cannot be read.
        """
        import base64

        logger.info("Reading remote file: %s", remote_path)

        # Use base64 to safely transfer binary content
        result = ssh.execute(f"base64 {remote_path}")
        if result.exit_code != 0:
            raise ImageBuildError(
                f"Failed to read remote file '{remote_path}': {result.stderr}"
            )

        try:
            return base64.b64decode(result.stdout)
        except Exception as e:
            raise ImageBuildError(
                f"Failed to decode remote file '{remote_path}': {e}"
            ) from e
