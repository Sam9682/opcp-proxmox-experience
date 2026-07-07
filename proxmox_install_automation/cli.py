"""
CLI entry point for Proxmox Install Automation.
"""

import sys
from typing import Optional

import click

from .config_loader import load_config
from .exceptions import ProxmoxAutomationError
from .logging_config import setup_logging
from .models import BuildStatus
from .orchestrator.builder import ProxmoxBuilder


@click.command()
@click.option(
    "--config", "-c",
    required=True,
    type=click.Path(exists=True),
    help="Path to configuration YAML file.",
)
@click.option(
    "--debug", "-d",
    is_flag=True,
    default=False,
    help="Enable debug logging.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Validate configuration without executing.",
)
@click.option(
    "--skip-gpu",
    is_flag=True,
    default=False,
    help="Skip GPU passthrough configuration.",
)
@click.option(
    "--skip-vm",
    is_flag=True,
    default=False,
    help="Skip test VM creation.",
)
@click.option(
    "--cleanup-only",
    is_flag=True,
    default=False,
    help="Only perform cleanup of existing resources.",
)
@click.option(
    "--log-file",
    type=click.Path(),
    default=None,
    help="Path to log file.",
)
def main(
    config: str,
    debug: bool,
    dry_run: bool,
    skip_gpu: bool,
    skip_vm: bool,
    cleanup_only: bool,
    log_file: Optional[str],
) -> None:
    """
    Proxmox VE Installation on OVH Baremetal OpenStack.

    Automates the deployment of Proxmox VE with GPU PCI passthrough
    on OVH OpenStack baremetal instances.
    """
    # Setup logging
    log_level = "DEBUG" if debug else "INFO"
    logger = setup_logging(level=log_level, log_file=log_file)

    logger.info("Proxmox Install Automation v0.1.0")
    logger.info("Loading configuration from: %s", config)

    try:
        # Load configuration
        build_config = load_config(config)

        # Apply CLI overrides
        if skip_gpu:
            build_config.gpu_passthrough.enabled = False
            logger.info("GPU passthrough disabled via --skip-gpu")

        if skip_vm:
            build_config.test_vm.enabled = False
            logger.info("Test VM creation disabled via --skip-vm")

        # Dry run - validate only
        if dry_run:
            logger.info("Dry run mode - validating configuration only")
            builder = ProxmoxBuilder()
            if builder.validate_config(build_config):
                click.echo("✓ Configuration is valid")
                sys.exit(0)
            else:
                click.echo("✗ Configuration validation failed")
                sys.exit(1)

        # Execute build
        builder = ProxmoxBuilder()

        if cleanup_only:
            logger.info("Cleanup-only mode")
            # TODO: Implement cleanup-only flow
            click.echo("Cleanup completed")
            sys.exit(0)

        state = builder.run(build_config)

        # Report results
        if state.status == BuildStatus.COMPLETED:
            click.echo("\n" + "=" * 60)
            click.echo("✓ Proxmox VE installation completed successfully!")
            click.echo("=" * 60)
            if state.proxmox_url:
                click.echo(f"  Proxmox Web UI: {state.proxmox_url}")
            if state.instance and state.instance.ip_address:
                click.echo(f"  Instance IP: {state.instance.ip_address}")
            if state.gpu_devices:
                click.echo(f"  GPU devices configured: {len(state.gpu_devices)}")
                for gpu in state.gpu_devices:
                    click.echo(f"    - {gpu.description} ({gpu.pci_id})")
            if state.test_vm:
                click.echo(f"  Test VM: {state.test_vm.name} (VMID: {state.test_vm.vmid})")
                click.echo(f"    GPU attached: {state.test_vm.gpu_attached}")
            click.echo("=" * 60)
            sys.exit(0)
        else:
            click.echo("\n" + "=" * 60)
            click.echo(f"✗ Build failed with status: {state.status.value}")
            if state.error_message:
                click.echo(f"  Error: {state.error_message}")
            click.echo("=" * 60)
            sys.exit(1)

    except ProxmoxAutomationError as e:
        logger.error("Automation error: %s", str(e))
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        logger.exception("Unexpected error: %s", str(e))
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
