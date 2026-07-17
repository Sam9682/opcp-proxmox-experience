"""
Instance management for the image building pipeline.

Handles creating, polling, and deleting OpenStack compute instances
used as temporary build environments for Proxmox qcow2 images.
"""

import time

from openstack.connection import Connection

from ..exceptions import InstanceCreationError
from ..logging_config import get_logger

logger = get_logger("image_builder.instance")


def generate_instance_name(timestamp: int) -> str:
    """
    Generate a unique instance name from a unix timestamp.

    Args:
        timestamp: Integer seconds since epoch.

    Returns:
        Instance name in format `proxmox-installer-{timestamp}`.
    """
    return f"proxmox-installer-{timestamp}"


class ImageBuildInstanceManager:
    """
    Manages the lifecycle of OpenStack compute instances for image building.

    Handles instance creation, polling for ACTIVE status, and deletion
    on error or timeout conditions.
    """

    def __init__(self, connection: Connection) -> None:
        """
        Initialize with an OpenStack SDK Connection.

        Args:
            connection: An authenticated OpenStack SDK Connection object.
        """
        self._conn = connection

    def create_instance(
        self,
        image_name: str,
        flavor_name: str,
        network_name: str,
        ssh_key_name: str,
    ) -> dict:
        """
        Create a build instance on OpenStack.

        Generates a unique name using the current unix timestamp,
        resolves image/flavor/network by name, and creates the server.

        Args:
            image_name: Name of the base image in OpenStack.
            flavor_name: Name of the compute flavor.
            network_name: Name of the network to attach.
            ssh_key_name: Name of the SSH key pair.

        Returns:
            A dict with 'id', 'name', and 'status' of the created server.

        Raises:
            InstanceCreationError: If image, flavor, or network is not found,
                or if the server creation API call fails.
        """
        instance_name = generate_instance_name(int(time.time()))
        logger.info(
            "Creating build instance '%s' with image='%s', flavor='%s', "
            "network='%s', key='%s'",
            instance_name,
            image_name,
            flavor_name,
            network_name,
            ssh_key_name,
        )

        try:
            image = self._conn.compute.find_image(image_name)
            if image is None:
                raise InstanceCreationError(
                    f"Image '{image_name}' not found"
                )

            flavor = self._conn.compute.find_flavor(flavor_name)
            if flavor is None:
                raise InstanceCreationError(
                    f"Flavor '{flavor_name}' not found"
                )

            network = self._conn.network.find_network(network_name)
            if network is None:
                raise InstanceCreationError(
                    f"Network '{network_name}' not found"
                )

            server = self._conn.compute.create_server(
                name=instance_name,
                image_id=image.id,
                flavor_id=flavor.id,
                networks=[{"uuid": network.id}],
                key_name=ssh_key_name,
            )

            logger.info(
                "Instance '%s' created with id='%s'",
                instance_name,
                server.id,
            )

            return {
                "id": server.id,
                "name": instance_name,
                "status": server.status,
            }

        except InstanceCreationError:
            raise
        except Exception as e:
            raise InstanceCreationError(
                f"Failed to create build instance '{instance_name}': {e}"
            ) from e

    def wait_for_active(
        self,
        server_id: str,
        server_name: str,
        timeout: int = 600,
        poll_interval: int = 10,
    ) -> dict:
        """
        Poll instance status until ACTIVE, ERROR, or timeout.

        On ERROR status or timeout, the instance is deleted before raising.

        Args:
            server_id: The OpenStack server ID.
            server_name: The server name (used in error messages).
            timeout: Maximum seconds to wait (default 600).
            poll_interval: Seconds between status checks (default 10).

        Returns:
            A dict with 'id', 'name', 'status', and 'addresses' of the
            ACTIVE server.

        Raises:
            InstanceCreationError: If the instance enters ERROR status
                or the timeout is exceeded. The instance is deleted in
                both cases.
        """
        logger.info(
            "Waiting for instance '%s' to become ACTIVE (timeout: %ds)",
            server_name,
            timeout,
        )
        start_time = time.time()

        while time.time() - start_time < timeout:
            server = self._conn.compute.get_server(server_id)
            status = server.status.upper()

            if status == "ACTIVE":
                logger.info("Instance '%s' is ACTIVE", server_name)
                return {
                    "id": server.id,
                    "name": server_name,
                    "status": "ACTIVE",
                    "addresses": server.addresses or {},
                }

            if status == "ERROR":
                logger.error(
                    "Instance '%s' entered ERROR status", server_name
                )
                self.delete_instance(server_id, server_name)
                raise InstanceCreationError(
                    f"Instance '{server_name}' entered ERROR status"
                )

            logger.debug(
                "Instance '%s' status: %s, waiting %ds...",
                server_name,
                status,
                poll_interval,
            )
            time.sleep(poll_interval)

        # Timeout reached
        elapsed = int(time.time() - start_time)
        logger.error(
            "Instance '%s' did not become ACTIVE within %ds (elapsed: %ds)",
            server_name,
            timeout,
            elapsed,
        )
        self.delete_instance(server_id, server_name)
        raise InstanceCreationError(
            f"Instance '{server_name}' did not become ACTIVE "
            f"within {timeout}s"
        )

    def delete_instance(self, server_id: str, server_name: str) -> bool:
        """
        Delete a compute instance.

        Args:
            server_id: The OpenStack server ID to delete.
            server_name: The server name (used in log messages).

        Returns:
            True if deletion succeeded, False otherwise.
        """
        logger.info("Deleting instance '%s' (%s)", server_name, server_id)
        try:
            self._conn.compute.delete_server(server_id, force=True)
            logger.info("Instance '%s' deletion initiated", server_name)
            return True
        except Exception as e:
            logger.warning(
                "Failed to delete instance '%s': %s", server_name, e
            )
            return False
