"""IP whitelist middleware for restricting access by IP address or CIDR range."""

import ipaddress
import logging
from typing import Optional

logger = logging.getLogger("taskplanner.ip_filter")


def normalize_client_ip(ip_str: str) -> str:
    """Normalize IP address string (strip whitespace)."""
    return (ip_str or "").strip()


def validate_ip_or_cidr(ip_str: str) -> bool:
    """Validate if string is a valid IP address or CIDR range."""
    try:
        ip_str = normalize_client_ip(ip_str)
        if "/" in ip_str:
            ipaddress.ip_network(ip_str, strict=False)
        else:
            ipaddress.ip_address(ip_str)
        return True
    except (ValueError, ipaddress.AddressValueError):
        return False


def _is_loopback(ip_str: str) -> bool:
    """Check if IP is loopback (127.0.0.1 or ::1)."""
    try:
        return ipaddress.ip_address(ip_str).is_loopback
    except (ValueError, ipaddress.AddressValueError):
        return False


class IPWhitelistMiddleware:
    """IP whitelist middleware for HTTP access control."""

    def __init__(self) -> None:
        self._allowed: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        self._enabled = False

    def update(self, allowed_ips: list[str]) -> None:
        """Update the whitelist from a list of IP addresses and CIDR ranges.
        
        Args:
            allowed_ips: List of IP addresses or CIDR ranges. Empty list disables whitelist.
        """
        if not allowed_ips:
            self._enabled = False
            self._allowed = []
            logger.info("IP whitelist disabled")
            return

        networks = []
        for ip_str in allowed_ips:
            ip_str = normalize_client_ip(ip_str)
            if not ip_str:
                continue
            try:
                if "/" in ip_str:
                    network = ipaddress.ip_network(ip_str, strict=False)
                else:
                    network = ipaddress.ip_network(ip_str)
                networks.append(network)
            except (ValueError, ipaddress.AddressValueError) as e:
                logger.warning(f"Invalid IP/CIDR '{ip_str}': {e}")
                raise ValueError(f"Invalid IP/CIDR '{ip_str}': {e}")

        self._allowed = networks
        self._enabled = True
        logger.info(f"IP whitelist enabled with {len(networks)} entries")

    def effective_client_ip(self, peer_host: Optional[str]) -> Optional[str]:
        """Extract the effective client IP from peer host.
        
        Args:
            peer_host: The TCP peer host (from request.client.host)
            
        Returns:
            Effective client IP or None if cannot determine.
        """
        return normalize_client_ip(peer_host) if peer_host else None

    def _is_allowed(self, client_ip: str) -> bool:
        """Check if client IP is allowed.
        
        Args:
            client_ip: The client IP address to check
            
        Returns:
            True if allowed, False otherwise.
        """
        if not self._enabled:
            return True

        # Loopback always allowed
        if _is_loopback(client_ip):
            return True

        # Check against whitelist
        try:
            ip_obj = ipaddress.ip_address(client_ip)
            for network in self._allowed:
                if ip_obj in network:
                    return True
        except (ValueError, ipaddress.AddressValueError):
            logger.warning(f"Invalid client IP format: {client_ip}")
            return False

        return False

    def is_allowed(self, client_ip: str) -> bool:
        """Public method to check if IP is allowed."""
        return self._is_allowed(client_ip)
