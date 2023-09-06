"""Create ContainerImage resource in Pyxis"""
import argparse
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Tuple
from urllib.parse import quote, urljoin

from operatorcert import pyxis
from operatorcert.logger import setup_logger

LOGGER = logging.getLogger("operator-cert")


def setup_argparser() -> Any:  # pragma: no cover
    """
    Setup argument parser

    Returns:
        Any: Initialized argument parser
    """
    parser = argparse.ArgumentParser(description="ContainerImage resource creator.")

    parser.add_argument(
        "--pyxis-url",
        default="https://pyxis.engineering.redhat.com",
        help="Base URL for Pyxis container metadata API",
    )
    parser.add_argument(
        "--isv-pid",
        help="isv_pid of the certification project from Red Hat Connect",
        required=True,
    )
    parser.add_argument(
        "--connect-registry",
        help="Connect registry host",
        required=True,
    )
    parser.add_argument(
        "--repository",
        help="Repository name assigned to certification project from Red Hat Connect",
        required=True,
    )
    parser.add_argument(
        "--certified", help="Is the ContainerImage certified?", required=True
    )
    parser.add_argument(
        "--bundle-version",
        help="Operator bundle version",
        required=True,
    )
    parser.add_argument(
        "--docker-image-digest",
        help="Container Image digest of related Imagestream",
        required=True,
    )
    parser.add_argument(
        "--skopeo-result",
        help="File with result of `skopeo inspect` running against image"
        " represented by ContainerImage to be created",
        required=True,
    )
    parser.add_argument(
        "--podman-result",
        help="File with result of `podman image inspect` running against image"
        " represented by ContainerImage to be created",
        required=True,
    )
    parser.add_argument("--is-latest", help="Is given version latest?", required=True)
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    return parser


def check_if_image_already_exists(args: Any) -> bool:
    """
    Check if image with given docker_image_digest and isv_pid already exists

    Args:
        args (Any): CLI arguments

    Returns:
        bool: True if image already exists, False otherwise
    """
    # quote is needed to urlparse the quotation marks
    filter_str = quote(
        f'isv_pid=="{args.isv_pid}";'
        f'docker_image_digest=="{args.docker_image_digest}";'
        f"not(deleted==true)"
    )

    check_url = urljoin(args.pyxis_url, f"v1/images?page_size=1&filter={filter_str}")

    # Get the list of the ContainerImages with given parameters
    rsp = pyxis.get(check_url)
    rsp.raise_for_status()

    query_results = rsp.json()["data"]

    if len(query_results) == 0:
        LOGGER.info(
            "Image with given docker_image_digest and isv_pid doesn't exist yet"
        )
        return False

    LOGGER.info(
        "Image with given docker_image_digest and isv_pid already exists."
        "Skipping the image creation."
    )
    return True


def prepare_parsed_data(skopeo_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prepare parsed_data for ContainerImage

    Args:
        skopeo_result (Dict[str, Any]): Skopeo inspect result

    Returns:
        Dict[str, Any]: Parsed data section of ContainerImage
    """
    parsed_data = {
        "docker_version": skopeo_result.get("DockerVersion", ""),
        "layers": skopeo_result.get("Layers", []),
        "architecture": skopeo_result.get("Architecture", ""),
        "env_variables": skopeo_result.get("Env", []),
    }

    return parsed_data


def create_container_image(
    args: Any, skopeo_result: Dict[str, Any], podman_result: List[Dict[str, Any]]
) -> Any:
    """
    Create ContainerImage resource in Pyxis

    Args:
        args (Any): CLI arguments
        skopeo_result (Dict[str, Any]): Skopeo inspect result
        podman_result (List[Dict[str, Any]]): Podman inspect result

    Returns:
        Any: Pyxis POST response
    """
    LOGGER.info("Creating new container image")

    date_now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")
    parsed_data = prepare_parsed_data(skopeo_result)

    upload_url = urljoin(args.pyxis_url, "v1/images")
    container_image_payload = {
        "isv_pid": args.isv_pid,
        "repositories": [
            {
                "published": True,
                "registry": args.connect_registry,
                "repository": args.repository,
                "push_date": date_now,
                "tags": [
                    {
                        "added_date": date_now,
                        "name": args.bundle_version,
                    },
                ],
            }
        ],
        "certified": True,
        "docker_image_digest": args.docker_image_digest,
        "image_id": args.docker_image_digest,
        "architecture": parsed_data["architecture"],
        "parsed_data": parsed_data,
        "sum_layer_size_bytes": int(podman_result[0]["Size"]),
    }

    if args.is_latest == "true":
        container_image_payload["repositories"][0]["tags"].append(
            {
                "added_date": date_now,
                "name": "latest",
            }
        )

    return pyxis.post(upload_url, container_image_payload)


def clean_latest_tag(repositories: List[Any]) -> Tuple[List[Any], bool]:
    """
    Clean LATEST tag from repositories

    Args:
        repositories (List[Any]): List of repositories

    Returns:
        _type_: List[Any]: List of repositories without LATEST tag and
        flag if LATEST
    """
    new_repositories = []
    is_latest = False
    for repo in repositories:
        new_tags = []
        for tag in repo["tags"]:
            if tag["name"] != "latest":
                new_tags.append(tag)
            else:
                is_latest = True
        repo["tags"] = new_tags
        new_repositories.append(repo)

    return new_repositories, is_latest


def remove_latest_from_previous_image(pyxis_url: str, isv_pid: str) -> None:
    """
    Remove LATEST tag from previous image

    Args:
        pyxis_url (str): Pyxis URL
        isv_pid (str): ISV pid which is used to identify the image
    """
    # quote is needed to urlparse the quotation marks
    filter_str = quote(f'isv_pid=="{isv_pid}";' "not(deleted==true)")

    # If there are multiple results, we only want the most recent one- we enforce
    # it by sorting by creation_date and getting only the first result.
    get_previous_image_url = urljoin(
        pyxis_url,
        f"v1/images?filter={filter_str}" f"&sort_by=creation_date[desc]&page_size=1",
    )
    # Get the list of the ContainerImages with given parameters
    rsp = pyxis.get(get_previous_image_url)
    rsp.raise_for_status()

    query_results = rsp.json()["data"]

    if len(query_results) == 0:
        LOGGER.info("It's the first image for this cert project")
        return

    LOGGER.info("Found previous image")

    prev_image = query_results[0]
    new_repositories, is_latest = clean_latest_tag(prev_image["repositories"])
    if is_latest:
        LOGGER.info("Removing LATEST tag")
        prev_image["repositories"] = new_repositories

        put_image_url = urljoin(pyxis_url, f"v1/images/id/{prev_image['_id']}")

        pyxis.put(put_image_url, prev_image)


def main() -> None:  # pragma: no cover
    """
    Main func
    """

    parser = setup_argparser()
    args = parser.parse_args()
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logger(level=log_level)

    with open(args.skopeo_result, encoding="utf-8") as json_file:
        skopeo_result = json.load(json_file)

    with open(args.podman_result, encoding="utf-8") as json_file:
        podman_result = json.load(json_file)

    exists = check_if_image_already_exists(args)

    if not exists:
        if args.is_latest == "true":
            remove_latest_from_previous_image(args.pyxis_url, args.isv_pid)
        create_container_image(args, skopeo_result, podman_result)


if __name__ == "__main__":  # pragma: no cover
    main()
