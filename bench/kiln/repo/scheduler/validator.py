"""Safety checks applied to every compiled profile before it can reach a kiln."""

MAX_TEMP_DEFAULT = 1285  # degrees C, controller hard limit (also const MAX_TEMP in common.kiln)


class LimitError(Exception):
    """Raised for E104 (target above MAX_TEMP) and similar limit violations."""


def check_limits(segments: list[dict], max_temp: int = MAX_TEMP_DEFAULT) -> None:
    """Reject any segment whose target temperature exceeds ``max_temp``.

    Added after the 2026-05-19 overfire on k2, where a typo wrote 1322 instead of 1222.
    Every segment, including those produced by macro expansion, must pass through here.
    """
    for seg in segments:
        target = seg["target_c"]
        if target > max_temp:
            raise LimitError(
                f"E104 segment {seg['name']!r}: target {target} C exceeds MAX_TEMP {max_temp} C"
            )
        if seg["rate_c_per_h"] == 0 and seg["hold_min"] == 0:
            raise LimitError(f"E105 segment {seg['name']!r}: does nothing")


def check_kiln_known(profile_kiln: str, known: list[str]) -> None:
    """Raise E202 when a profile header names a kiln that is not defined."""
    if profile_kiln not in known:
        raise LimitError(f"E202 unknown kiln {profile_kiln!r}; defined: {', '.join(known)}")
