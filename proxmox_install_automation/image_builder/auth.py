"""
Authentication extension for the image building pipeline.

Wraps the existing OpenStackAuthManager and adds service endpoint verification
for Compute, Image, and Network services required by the image build pipeline.
"""

import signal
from typing import List

from openstack.connection import Connection

from ..auth.manager import OpenStackAuthManager
from ..exceptions import AuthenticationError
from ..logging_config import get_logger
from ..models import Credentials

logger = get_logger("image_builder.auth")

# Required fields for each authentication method
_APP_CREDENTIAL_REQUIRED_FIELDS = [
    "auth_url",
    "region",
    "application_credential_id",
    "application_credential_secret",
]

_PASSWORD_REQUIRED_FIELDS = [
    "auth_url",
    "region",
    "username",
    "password",
    "project_name",
]

# Services that must be reachable for the image build pipeline
_REQUIRED_SERVICES = ["compute", "image", "network"]

# Authentication timeout in seconds
_AUTH_TIMEOUT_SECONDS = 30


class _AuthTimeoutError(Exception):
    """Internal timeout signal for authentication."""

    pass


class ImageBuildAuthManager:
    """
    Authentication manager for the image building pipeline.

    Wraps the existing OpenStackAuthManager and adds:
    - Credential field validation before connection attempt
    - Service endpoint verification (Compute, Image, Network)
    - 30-second authentication timeout
    - Descriptive error messages with auth_url, service name, and reason
    """

    def __init__(self) -> None:
        self._auth_manager = OpenStackAuthManager()
        self._connection: Connection | None = None

    def authenticate(self, credentials: Credentials) -> Connection:
        """
        Authenticate to OpenStack and verify required service endpoints.

        Validates credential fields, authenticates using the underlying
        OpenStackAuthManager, then verifies connectivity to Compute, Image,
        and Network services.

        Args:
            credentials: OpenStack credentials for authentication.

        Returns:
            Authenticated OpenStack Connection object.

        Raises:
            AuthenticationError: If credential fields are missing, authentication
                fails, or any required service endpoint is unreachable. The error
                message includes the auth_url, failing service name, and reason.
        """
        # Step 1: Validate required credential fields
        self._validate_credentials(credentials)

        # Step 2: Authenticate with timeout
        auth_url = credentials.auth_url
        logger.info(
            "Authenticating to OpenStack for image building at %s", auth_url
        )

        try:
            connection = self._authenticate_with_timeout(credentials)
        except _AuthTimeoutError:
            raise AuthenticationError(
                f"Authentication timed out after {_AUTH_TIMEOUT_SECONDS} seconds. "
                f"auth_url={auth_url}, service=authentication, "
                f"reason=timeout exceeded {_AUTH_TIMEOUT_SECONDS}s"
            )
        except AuthenticationError:
            raise
        except Exception as e:
            raise AuthenticationError(
                f"Authentication failed. "
                f"auth_url={auth_url}, service=authentication, "
                f"reason={e}"
            ) from e

        # Step 3: Verify connectivity to required services
        self._verify_services(connection, auth_url)

        self._connection = connection
        logger.info("Successfully authenticated and verified all services")
        return connection

    @property
    def connection(self) -> Connection:
        """Get the current authenticated connection."""
        if self._connection is None:
            raise AuthenticationError("Not authenticated. Call authenticate() first.")
        return self._connection

    def _validate_credentials(self, credentials: Credentials) -> None:
        """
        Validate that all required credential fields are present and non-empty.

        Args:
            credentials: Credentials to validate.

        Raises:
            AuthenticationError: If required fields are missing or empty.
        """
        if credentials.auth_type == "v3applicationcredential":
            required_fields = _APP_CREDENTIAL_REQUIRED_FIELDS
        else:
            required_fields = _PASSWORD_REQUIRED_FIELDS

        missing_fields: List[str] = []
        for field_name in required_fields:
            value = getattr(credentials, field_name, None)
            if not value or (isinstance(value, str) and not value.strip()):
                missing_fields.append(field_name)

        if missing_fields:
            auth_url = credentials.auth_url or "<not provided>"
            raise AuthenticationError(
                f"Missing required credential fields: {', '.join(missing_fields)}. "
                f"auth_url={auth_url}, service=authentication, "
                f"reason=missing fields: {', '.join(missing_fields)}"
            )

    def _authenticate_with_timeout(self, credentials: Credentials) -> Connection:
        """
        Authenticate with a timeout of 30 seconds.

        Uses signal-based timeout on Unix systems. Falls back to direct
        authentication without timeout enforcement on non-Unix systems.

        Args:
            credentials: OpenStack credentials.

        Returns:
            Authenticated Connection object.

        Raises:
            _AuthTimeoutError: If authentication exceeds the timeout.
            AuthenticationError: If authentication fails.
        """

        def _timeout_handler(signum, frame):
            raise _AuthTimeoutError()

        # Try signal-based timeout (Unix only)
        old_handler = None
        try:
            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(_AUTH_TIMEOUT_SECONDS)
            connection = self._auth_manager.authenticate(credentials)
            signal.alarm(0)  # Cancel alarm
            return connection
        except _AuthTimeoutError:
            raise
        except AttributeError:
            # signal.SIGALRM not available (Windows) - proceed without timeout
            return self._auth_manager.authenticate(credentials)
        finally:
            if old_handler is not None:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)

    def _verify_services(self, connection: Connection, auth_url: str) -> None:
        """
        Verify connectivity to Compute, Image, and Network services.

        Issues a test API call to each service endpoint to confirm reachability.

        Args:
            connection: Authenticated OpenStack connection.
            auth_url: The authentication URL (for error messages).

        Raises:
            AuthenticationError: If any service endpoint is unreachable,
                including auth_url, service name, and reason.
        """
        service_checks = {
            "compute": self._check_compute_service,
            "image": self._check_image_service,
            "network": self._check_network_service,
        }

        for service_name, check_fn in service_checks.items():
            try:
                check_fn(connection)
                logger.debug("Service '%s' is reachable", service_name)
            except Exception as e:
                raise AuthenticationError(
                    f"Service endpoint verification failed. "
                    f"auth_url={auth_url}, service={service_name}, "
                    f"reason={e}"
                ) from e

    def _check_compute_service(self, connection: Connection) -> None:
        """Verify Compute service by listing flavors (lightweight call)."""
        # Use a limited list call to verify the endpoint is reachable
        list(connection.compute.flavors(limit=1))

    def _check_image_service(self, connection: Connection) -> None:
        """Verify Image service by listing images (lightweight call)."""
        list(connection.image.images(limit=1))

    def _check_network_service(self, connection: Connection) -> None:
        """Verify Network service by listing networks (lightweight call)."""
        list(connection.network.networks(limit=1))
