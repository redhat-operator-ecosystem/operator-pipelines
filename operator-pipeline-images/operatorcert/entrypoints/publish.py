"""
Script for publishing bundle related entities
"""
import argparse
import logging
import textwrap
from typing import Any, Dict
from urllib.parse import urljoin

import html2text
from operatorcert import pyxis
from operatorcert.logger import setup_logger

LOGGER = logging.getLogger("operator-cert")


def setup_argparser() -> Any:
    """
    Setup argument parser

    Returns:
        Any: Initialized argument parser
    """
    parser = argparse.ArgumentParser(description="Publishing cli tool.")

    parser.add_argument(
        "--pyxis-url",
        default="https://pyxis.engineering.redhat.com/",
        help="Base URL for Pyxis container metadata API",
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose output")

    sub_parsers = parser.add_subparsers()
    vendor_parser = sub_parsers.add_parser("vendor")
    repository_parser = sub_parsers.add_parser("repository")

    vendor_parser.set_defaults(func=publish_vendor)
    repository_parser.set_defaults(func=publish_repository)

    vendor_parser.add_argument(
        "--org-id",
        required=True,
        help="Organization ID",
    )

    repository_parser.add_argument(
        "--cert-project-id", help="Certification project ID", required=True
    )

    repository_parser.add_argument(
        "--connect-registry", help="Connect registry host", required=True
    )

    return parser


def publish_vendor(args: Any) -> Any:
    """
    Publish container vendor

    Args:
        args (Any): CLI arguments

    Returns:
        Any: Vendor object
    """
    LOGGER.info("Publishing vendor...")
    vendor = pyxis.get_vendor_by_org_id(args.pyxis_url, args.org_id)

    identifier = vendor.get("_id")
    published = vendor.get("published", False)
    if published:
        LOGGER.info("Vendor %s is already published", identifier)
        return vendor

    patch_vendor_url = urljoin(
        args.pyxis_url,
        f"v1/vendors/id/{identifier}",
    )
    payload = {"published": True}

    resp = pyxis.patch(patch_vendor_url, payload)
    LOGGER.info("Vendor %s is published now", identifier)
    return resp


def publish_repository(args: Any) -> Any:
    """
    Publish container repository.
    The function either set a published flag for existing repository or
    create a new repository based on project's data.

    Args:
        args (Any): CLI arguments

    Returns:
        Any: Repository object
    """
    LOGGER.info("Publishing repository...")
    project = pyxis.get_project(args.pyxis_url, args.cert_project_id)
    isv_pid = project.get("container", {}).get("isv_pid")

    repository = pyxis.get_repository_by_isv_pid(args.pyxis_url, isv_pid)
    if repository:
        repo_id = repository.get("_id")
        LOGGER.info("Repository already exists: %s", repo_id)
        published = repository.get("published", False)
        if published:
            LOGGER.info("Repository is already published")
            return repository
        patch_repo_url = urljoin(
            args.pyxis_url,
            f"v1/repositories/id/{repo_id}",
        )
        payload = {"published": True}

        repo_resp = pyxis.patch(patch_repo_url, payload)
        LOGGER.info("Repository %s is published now", repo_id)
        return repo_resp
    return create_repository(args, project)


def create_repository(args: Any, project: Dict[str, Any]) -> Any:
    """
    Create a new container repository for given project

    Args:
        args (Any): CLI arguments
        project (Dict[str, Any]): Certification project

    Returns:
        Any: A new container repository object
    """
    LOGGER.info("Creating repository")

    container = project.get("container", {})
    distribution_type = container.get("distribution_method")

    if distribution_type not in ["rhcc", "marketplace_only"]:
        LOGGER.warning(
            "Unsupported distribution type for operator project: %s", distribution_type
        )
        return None

    vendor = pyxis.get_vendor_by_org_id(args.pyxis_url, project.get("org_id") or "")
    vendor_label = vendor["label"]

    repo_name = container.get("repository_name")
    repository_name = f"{vendor_label}/{repo_name}"

    long_description = container.get("repository_description") or " "
    # strip html, trim by word boundary, max length 100, add ellipsis
    short_description = html2text.html2text(long_description)
    short_description = textwrap.shorten(short_description, 97, placeholder="...")

    display_data = {
        "name": project.get("name", ""),
        "long_description": long_description,
        "short_description": short_description,
    }

    repository = {
        "release_categories": [container.get("release_category")],
        "display_data": display_data,
        "non_production_only": False,
        "privileged_images_allowed": container.get("privileged", False),
        "protected_for_pull": False,
        "protected_for_search": False,
        "registry": args.connect_registry,
        "repository": repository_name,
        "build_categories": ["Operator bundle"],
        "isv_pid": container.get("isv_pid"),
        "application_categories": container.get("application_categories", []),
        "includes_multiple_content_streams": False,
        "published": True,
        "vendor_label": vendor_label,
    }

    post_repository_url = urljoin(
        args.pyxis_url,
        "v1/repositories",
    )

    resp = pyxis.post(post_repository_url, repository)
    LOGGER.info("A new repository has been created: %s", resp["_id"])
    return resp


def main() -> None:  # pragma: no cover
    """
    Main function
    """
    parser = setup_argparser()
    args = parser.parse_args()

    log_level = "INFO"
    if args.verbose:
        log_level = "DEBUG"
    setup_logger(level=log_level)

    args.func(args)


if __name__ == "__main__":  # pragma: no cover
    main()
