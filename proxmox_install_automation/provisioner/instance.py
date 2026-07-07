"""
Baremetal instance provisioner for OVH OpenStack.
"""

import time
from typing import Optional

from openstack.connection import Connection

from ..exceptions import InstanceCreationError, InstanceError
from ..logging_config import get_logger
from ..models import Instance, InstanceSpec

logger = get_logger("provisioner.instance")


class InstanceProvisioner:
    """Manages the lifecycle of OVH OpenStack baremetal instances."""

    def __init__(self, connection: Connection) -> None:
        self._conn = connection

    def create_instance(self, spec: InstanceSpec) -> Instance:
        """
        Create a baremetal instance on OVH OpenStack.

        Args:
            spec: Instance specification.

        Returns:
            Created Instance object.

        Raises:
            InstanceCreationError: If instance creation fails.
        """
        instance_name = f"proxmox-installer-{int(time.time())}"
        logger.info(
            "Creating instance '%s' with flavor '%s' and image '%s'",
            instance_name,
            spec.flavor_name,
            spec.base_image_name,
        )

        try:
            # Find the image
            image = self._conn.compute.find_image(spec.base_image_name)
            if image is None:
                raise InstanceCreationError(
                    f"Image '{spec.base_image_name}' not found"
                )

            # Find the flavor
            flavor = self._conn.compute.find_flavor(spec.flavor_name)
            if flavor is None:
                raise InstanceCreationError(
                    f"Flavor '{spec.flavor_name}' not found"
                )

            # Find the network
            network = self._conn.network.find_network(spec.network_name)
            if network is None:
                raise InstanceCreationError(
                    f"Network '{spec.network_name}' not found"
                )

            # Create the instance
            server_kwargs = {
                "name": instance_name,
                "image_id": image.id,
                "flavor_id": flavor.id,
                "networks": [{"uuid": network.id}],
                "key_name": spec.ssh_key_name,
            }

            if spec.security_groups:
                server_kwargs["security_groups"] = [
                    {"name": sg} for sg in spec.security_groups
                ]

            if spec.availability_zone:
                server_kwargs["availability_zone"] = spec.availability_zone

            server = self._conn.compute.create_server(**server_kwargs)

            return Instance(
                id=server.id,
                name=instance_name,
                status=server.status,
                flavor=spec.flavor_name,
            )

        except InstanceCreationError:
            raise
        except Exception as e:
            raise InstanceCreationError(
                f"Failed to create instance: {e}"
            ) from e

    def wait_for_ready(self, instance: Instance, timeout: int = 600) -> bool:
        """
        Wait for the instance to reach ACTIVE status.

        Args:
            instance: Instance to wait for.
            timeout: Timeout in seconds.

        Returns:
            True if instance becomes ACTIVE.

        Raises:
            InstanceError: If instance enters ERROR state.
            InstanceCreationError: If timeout is exceeded.
        """
        logger.info("Waiting for instance '%s' to be ready (timeout: %ds)", instance.name, timeout)
        start_time = time.time()
        poll_interval = 10

        while time.time() - start_time < timeout:
            server = self._conn.compute.get_server(instance.id)
            status = server.status.upper()

            if status == "ACTIVE":
                logger.info("Instance '%s' is ACTIVE", instance.name)
                instance.status = "ACTIVE"

                # Get IP address
                for network_name, addresses in (server.addresses or {}).items():
                    for addr in addresses:
                        if addr.get("version") == 4:
                            if addr.get("OS-EXT-IPS:type") == "floating":
                                instance.floating_ip = addr["addr"]
                            else:
                                instance.ip_address = addr["addr"]

                # Use floating IP if available, otherwise fixed IP
                if not instance.floating_ip and not instance.ip_address:
                    # Try to get any IP
                    for network_name, addresses in (server.addresses or {}).items():
                        for addr in addresses:
                            if addr.get("version") == 4:
                                instance.ip_address = addr["addr"]
                                break

                return True

            elif status == "ERROR":
                raise InstanceError(
                    f"Instance '{instance.name}' entered ERROR state"
                )

            logger.debug("Instance status: %s, waiting...", status)
            time.sleep(poll_interval)

        raise InstanceCreationError(
            f"Instance '{instance.name}' did not become ACTIVE within {timeout}s"
        )

    def get_instance_ip(self, instance: Instance) -> str:
        """
        Get the accessible IP address.

        Args:
            instance: Instance to get IP for.

        Returns:
            IP address string.
        """
        return instance.floating_ip or instance.ip_address or ""

    def destroy_instance(self, instance: Instance) -> bool:
        """
        Destroy the instance.

        Args:
            instance: Instance to destroy.

        Returns:
            True if successfully destroyed.
        """
        logger.info("Destroying instance '%s' (%s)", instance.name, instance.id)
        try:
            self._conn.compute.delete_server(instance.id, force=True)
            # Wait for deletion
            for _ in range(60):
                try:
                    server = self._conn.compute.get_server(instance.id)
                    if server is None:
                        break
                except Exception:
                    break
                time.sleep(5)
            logger.info("Instance '%s' destroyed", instance.name)
            return True
        except Exception as e:
            logger.warning("Failed to destroy instance: %s", e)
            return False
