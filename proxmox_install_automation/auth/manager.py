"""
OpenStack authentication manager.
"""

import openstack
from openstack.connection import Connection

from ..exceptions import AuthenticationError
from ..logging_config import get_logger
from ..models import Credentials

logger = get_logger("auth.manager")


class OpenStackAuthManager:
    """Manages OpenStack authentication and connection."""

    def __init__(self) -> None:
        self._connection: Connection | None = None

    def authenticate(self, credentials: Credentials) -> Connection:
        """
        Authenticate to OpenStack and return a connection.

        Args:
            credentials: OpenStack credentials.

        Returns:
            OpenStack Connection object.

        Raises:
            AuthenticationError: If authentication fails.
        """
        logger.info("Authenticating to OpenStack at %s", credentials.auth_url)

        try:
            auth_args = {
                "auth_url": credentials.auth_url,
                "region_name": credentials.region,
                "identity_api_version": credentials.identity_api_version,
                "interface": credentials.interface,
            }

            if credentials.auth_type == "v3applicationcredential":
                auth_args["auth_type"] = "v3applicationcredential"
                auth_args["application_credential_id"] = (
                    credentials.application_credential_id
                )
                auth_args["application_credential_secret"] = (
                    credentials.application_credential_secret
                )
            else:
                auth_args["username"] = credentials.username
                auth_args["password"] = credentials.password
                auth_args["project_name"] = credentials.project_name
                auth_args["user_domain_name"] = credentials.user_domain_name
                auth_args["project_domain_name"] = credentials.project_domain_name

            self._connection = openstack.connect(**auth_args)

            # Validate connection by listing projects
            self._connection.identity.get_token()
            logger.info("Successfully authenticated to OpenStack")
            return self._connection

        except Exception as e:
            raise AuthenticationError(
                f"Failed to authenticate with OpenStack: {e}"
            ) from e

    @property
    def connection(self) -> Connection:
        """Get the current connection."""
        if self._connection is None:
            raise AuthenticationError("Not authenticated. Call authenticate() first.")
        return self._connection

    def validate_connection(self) -> bool:
        """
        Validate the current connection is active.

        Returns:
            True if connection is valid.
        """
        if self._connection is None:
            return False
        try:
            self._connection.identity.get_token()
            return True
        except Exception:
            return False
