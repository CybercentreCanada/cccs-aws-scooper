from platform import platform

from core.utils.paginate import paginate

from .io import run_cmd
from .logging import LOGGER
from .sts import ORG_CLIENT


def enable_service_access(service_principal: str) -> None:
    """Enable integration of given service principal at organization level."""
    service_principals = paginate(
        client=ORG_CLIENT,
        command="list_aws_service_access_for_organization",
        array="EnabledServicePrincipals",
        logger=LOGGER,
    )

    for _service_principal in service_principals:
        if _service_principal["ServicePrincipal"] == service_principal:
            LOGGER.info("Trusted access already enabled for '%s'", service_principal)
            return

    LOGGER.info("Enabling trusted access for '%s'", service_principal)
    ORG_CLIENT.enable_aws_service_access(ServicePrincipal=service_principal)
    LOGGER.info("Successfully enabled trusted access for '%s'", service_principal)


def install_terraform() -> None:
    """Install Terraform if it's not already installed."""
    try:
        run_cmd("terraform --version")
    except FileNotFoundError:
        _platform = platform()
        # https://developer.hashicorp.com/terraform/install#linux
        if "amzn" in _platform:
            # Terraform Install for Amazon Linux
            LOGGER.info("Installing Terraform...")
            run_cmd("sudo yum install -y yum-utils shadow-utils")
            run_cmd(
                "sudo yum-config-manager --add-repo https://rpm.releases.hashicorp.com/AmazonLinux/hashicorp.repo"
            )
            run_cmd("sudo yum -y install terraform")
            run_cmd("terraform --version")
            LOGGER.info("Successfully installed Terraform!")
        else:
            LOGGER.error("Failed to automatically install Terraform on '%s'", _platform)
            raise NotImplementedError(
                f"Automated Terraform install not supported for '{_platform}'"
            )
