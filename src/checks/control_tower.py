"""Control Tower Checks (FR-5).

Checks Control Tower deployment status, drift, and version.
Only runs if the current account is the management account.
"""

import boto3
from botocore.exceptions import EndpointConnectionError

from src.discovery.regions import has_service_endpoint


def _list_landing_zones(client, opted_in_regions=()):
    """List landing zones, including those homed in an opt-in region.

    ListLandingZones returns a landing zone from any commercial region, but
    a landing zone whose home region is an opt-in region is returned only
    when called in that home region. When the default-region call finds
    nothing or fails, search each opted-in region. Opted-in regions that
    botocore's endpoint data lists without a Control Tower endpoint are
    skipped. Any other regional failure, including a connection failure,
    does not stop the search; the first such failure is raised only if no
    region returns a landing zone, so the check reports an error rather
    than a false absence.
    """
    first_error = None
    for region in (None, *opted_in_regions):
        try:
            regional = (
                client
                if region is None
                else boto3.client("controltower", region_name=region)
            )
            landing_zones = regional.list_landing_zones().get("landingZones", [])
        except Exception as e:
            no_endpoint = (
                region is not None
                and isinstance(e, EndpointConnectionError)
                and not has_service_endpoint("controltower", region)
            )
            if first_error is None and not no_endpoint:
                first_error = e
            continue
        if landing_zones:
            return landing_zones
    if first_error is not None:
        raise first_error
    return []


def _get_landing_zone_details(client, opted_in_regions=()):
    """Fetch landing zone details, honoring the landing zone's home region.

    When a landing zone's home region is opt-in, ListLandingZones returns
    its ARN only from that region. GetLandingZone must be called in the
    landing zone's home region. The home region is embedded in the ARN
    returned by ListLandingZones
    (arn:<partition>:controltower:<home-region>:<account>:landingzone/<id>).

    Returns:
        dict or None: landingZone details, or None if no landing zone exists
    """
    landing_zones = _list_landing_zones(client, opted_in_regions)
    if not landing_zones:
        return None

    lz_arn = landing_zones[0]["arn"]
    home_region = lz_arn.split(":")[3]
    regional_client = boto3.client("controltower", region_name=home_region)
    get_resp = regional_client.get_landing_zone(landingZoneIdentifier=lz_arn)
    return get_resp.get("landingZone", {})


def check_control_tower_deployed(opted_in_regions=()):
    """FR-5.1: Verify Control Tower is deployed (landing zone exists)."""
    try:
        client = boto3.client("controltower")
        landing_zones = _list_landing_zones(client, opted_in_regions)
        deployed = len(landing_zones) > 0
        return {
            "check": "Control Tower deployed",
            "description": "AWS Control Tower should be deployed for automated multi-account governance.",
            "status": "complete" if deployed else "incomplete",
            "required": True,
            "weight": 6,
            "loe": 6,
            "remediationLink": "https://docs.aws.amazon.com/controltower/latest/userguide/getting-started-with-control-tower.html",
        }
    except Exception as e:
        return {
            "check": "Control Tower deployed",
            "description": "AWS Control Tower should be deployed for automated multi-account governance.",
            "status": "error",
            "required": True,
            "weight": 6,
            "loe": 6,
            "remediationLink": "https://docs.aws.amazon.com/controltower/latest/userguide/getting-started-with-control-tower.html",
            "error": str(e),
        }


def check_control_tower_not_drifted(opted_in_regions=()):
    """FR-5.2: Verify Control Tower landing zone is not drifted."""
    try:
        client = boto3.client("controltower")
        landing_zone = _get_landing_zone_details(client, opted_in_regions)

        if landing_zone is None:
            return {
                "check": "Control Tower not drifted",
                "description": "Control Tower landing zone should not be in a drifted state.",
                "status": "incomplete",
                "required": True,
                "weight": 6,
                "loe": 2,
                "remediationLink": "https://docs.aws.amazon.com/controltower/latest/userguide/drift.html",
            }

        drift_status = (landing_zone.get("driftStatus") or {}).get("status")
        if drift_status not in ("IN_SYNC", "DRIFTED"):
            return {
                "check": "Control Tower not drifted",
                "description": "Control Tower landing zone should not be in a drifted state.",
                "status": "error",
                "required": True,
                "weight": 6,
                "loe": 2,
                "remediationLink": "https://docs.aws.amazon.com/controltower/latest/userguide/drift.html",
                "error": f"Landing zone drift status is unavailable ({drift_status or 'missing'}).",
            }
        not_drifted = drift_status == "IN_SYNC"

        return {
            "check": "Control Tower not drifted",
            "description": "Control Tower landing zone should not be in a drifted state.",
            "status": "complete" if not_drifted else "incomplete",
            "required": True,
            "weight": 6,
            "loe": 2,
            "remediationLink": "https://docs.aws.amazon.com/controltower/latest/userguide/drift.html",
        }
    except Exception as e:
        return {
            "check": "Control Tower not drifted",
            "description": "Control Tower landing zone should not be in a drifted state.",
            "status": "error",
            "required": True,
            "weight": 6,
            "loe": 2,
            "remediationLink": "https://docs.aws.amazon.com/controltower/latest/userguide/drift.html",
            "error": str(e),
        }


def check_control_tower_latest_version(opted_in_regions=()):
    """FR-5.3: Verify Control Tower is on the latest version."""
    try:
        client = boto3.client("controltower")
        landing_zone = _get_landing_zone_details(client, opted_in_regions)

        if landing_zone is None:
            return {
                "check": "Control Tower latest version",
                "description": "Control Tower landing zone should be on the latest available version.",
                "status": "incomplete",
                "required": False,
                "weight": 5,
                "loe": 2,
                "remediationLink": "https://docs.aws.amazon.com/controltower/latest/userguide/configuration-updates.html",
            }

        current_version = landing_zone.get("version", "")
        latest_version = landing_zone.get("latestAvailableVersion", "")
        is_latest = current_version == latest_version and current_version != ""

        return {
            "check": "Control Tower latest version",
            "description": "Control Tower landing zone should be on the latest available version.",
            "status": "complete" if is_latest else "incomplete",
            "required": False,
            "weight": 5,
            "loe": 2,
            "remediationLink": "https://docs.aws.amazon.com/controltower/latest/userguide/configuration-updates.html",
        }
    except Exception as e:
        return {
            "check": "Control Tower latest version",
            "description": "Control Tower landing zone should be on the latest available version.",
            "status": "error",
            "required": False,
            "weight": 5,
            "loe": 2,
            "remediationLink": "https://docs.aws.amazon.com/controltower/latest/userguide/configuration-updates.html",
            "error": str(e),
        }


def run_all(opted_in_regions=()):
    """Run all Control Tower checks (FR-5.1 through FR-5.3).

    Args:
        opted_in_regions: opt-in regions enabled for the account, searched
            when the default-region ListLandingZones call finds nothing or fails
    """
    return [
        check_control_tower_deployed(opted_in_regions),
        check_control_tower_not_drifted(opted_in_regions),
        check_control_tower_latest_version(opted_in_regions),
    ]
