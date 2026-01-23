
"""SOCKS5 proxy wrapper for routing LLM client's API traffic"""
import config
import requests
import logging
from contextlib import contextmanager
import socks
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)
if not logger.handlers:
    console_handler = logging.StreamHandler()
    formatter = logging.Formatter('[PROXY] %(levelname)s: %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

def set_proxy_log_level(level):
    logger.setLevel(level)

class ProxyWrapper:
    """Base class for proxy wrappers"""
    def __init__(self, proxy_url: Optional[str] = None):
        self.proxy_url = proxy_url
    
    @contextmanager
    def proxy_connection(self):
        raise NotImplementedError("Subclasses must implement proxy_connection")
    
    def get_session(self):
        raise NotImplementedError("Subclasses must implement get_session")
    
    def get_connection_info(self):
        raise NotImplementedError("Subclasses must implement get_connection_info")

class ProxyConfig:
    """Parse and store proxy configuration"""
    def __init__(self, proxy_url=None):
        self.proxy_host = None
        self.proxy_port = None
        self.proxy_user = None
        self.proxy_pass = None
        self.proxy_type = socks.SOCKS5
        
        if proxy_url:
            self._parse_proxy_url(proxy_url)
    
    def _parse_proxy_url(self, url):
        """Parse proxy URL in format: socks5://[user:pass@]host:port or http://[user:pass@]host:port"""
        try:
            url = url.rstrip('/')
            logger.debug(f"Parsing proxy URL: {url}")
            
            if '://' in url:
                protocol, rest = url.split('://', 1)
                if protocol.lower() in ['socks5', 'socks4']:
                    self.proxy_type = socks.SOCKS5 if protocol.lower() == 'socks5' else socks.SOCKS4
                elif protocol.lower() in ['http', 'https']:
                    self.proxy_type = 'http'
                else:
                    logger.error(f"Unsupported protocol: {protocol}")
                    return False
            else:
                rest = url
                self.proxy_type = socks.SOCKS5
            
            if '@' in rest:
                auth_part, host_part = rest.rsplit('@', 1)
                if ':' in auth_part:
                    self.proxy_user, self.proxy_pass = auth_part.split(':', 1)
                    logger.debug(f"Authentication found for user: {self.proxy_user}")
            else:
                host_part = rest
            
            if ':' in host_part:
                self.proxy_host, port_str = host_part.rsplit(':', 1)
                self.proxy_port = int(port_str.strip())
            else:
                self.proxy_host = host_part
                self.proxy_port = 1080
            
            logger.info(f"Parsed proxy: {self.proxy_host}:{self.proxy_port} (type: {self.proxy_type})")
            return True
            
        except Exception as e:
            logger.error(f"Error parsing proxy URL '{url}': {e}")
            return False
    
    def is_valid(self):
        return self.proxy_host is not None and self.proxy_port is not None
    
    def get_proxy_url(self):
        if not self.is_valid():
            return None
        
        protocol = 'http' if self.proxy_type == 'http' else 'socks5'
        if self.proxy_user and self.proxy_pass:
            proxy_url = f"{protocol}://{self.proxy_user}:{self.proxy_pass}@{self.proxy_host}:{self.proxy_port}"
        else:
            proxy_url = f"{protocol}://{self.proxy_host}:{self.proxy_port}"
        
        logger.debug(f"Generated proxy URL: {proxy_url}")
        return proxy_url

class SOCKSProxyWrapper(ProxyWrapper):
    """SOCKS5 proxy wrapper for LLM API requests"""
    def __init__(self, proxy_url=None):
        logging.info("using SOCKSProxyWrapper")
        super().__init__(proxy_url)
        self.proxy_config = None
        self.original_socket = None
        self.session = None
        
    def _setup_proxy_config(self):
        """Setup proxy configuration"""
        try:
            logger.debug("Setting up proxy configuration...")
            self.proxy_config = ProxyConfig(self.proxy_url)
            if not self.proxy_config.is_valid():
                raise ValueError("Invalid proxy configuration")
            logger.debug(f"Proxy configured: {self.proxy_config.proxy_host}:{self.proxy_config.proxy_port} (type: {self.proxy_config.proxy_type})")
            return True
        except Exception as e:
            logger.error(f"Failed to setup proxy config: {e}")
            return False
    
    def _test_proxy_connection(self):
        """Test proxy connection"""
        try:
            proxy_url = self.proxy_config.get_proxy_url()
            logger.debug(f"Testing proxy connection: {proxy_url}")
            session = requests.Session()
            session.proxies = {'http': proxy_url, 'https': proxy_url}
            session.timeout = 15
            test_urls = ['https://httpbin.org/ip', 'https://ipv4.webshare.io/', 'http://httpbin.org/ip']
            
            for test_url in test_urls:
                try:
                    logger.debug(f"Testing with URL: {test_url}")
                    response = session.get(test_url, timeout=10)
                    if response.status_code == 200:
                        logger.info("Proxy connection successful.")
                        return True
                except Exception as e:
                    logger.debug(f"Failed to test with {test_url}: {e}")
                    continue
            
            logger.warning("All proxy test URLs failed")
            return False
        except Exception as e:
            logger.error(f"Proxy connection test failed: {e}")
            return False
    
    @contextmanager
    def proxy_connection(self):
        """Context manager for proxy connection"""
        logger.info("Setting up proxy connection...")
        if not self._setup_proxy_config():
            raise RuntimeError("Failed to setup proxy configuration")
        if not self._test_proxy_connection():
            logger.warning("Proxy connection test failed, but continuing anyway...")
        
        self.session = requests.Session()
        proxy_url = self.proxy_config.get_proxy_url()
        self.session.proxies = {'http': proxy_url, 'https': proxy_url}
        self.session.timeout = 30
        
        try:
            logger.info(f"Proxy connection established: {self.proxy_config.proxy_host}:{self.proxy_config.proxy_port}")
            yield self
        finally:
            if self.session:
                self.session.close()
                self.session = None
    
    def get_session(self):
        return self.session
    
    def get_connection_info(self):
        if self.proxy_config:
            proxy_type_str = 'HTTP' if self.proxy_config.proxy_type == 'http' else 'SOCKS5' if self.proxy_config.proxy_type == socks.SOCKS5 else 'SOCKS4'
            return {
                'proxy_host': self.proxy_config.proxy_host,
                'proxy_port': self.proxy_config.proxy_port,
                'proxy_type': proxy_type_str,
                'proxy_url': self.proxy_url,
                'has_auth': bool(self.proxy_config.proxy_user),
                'mode': 'socks5_proxy'
            }
        return {'mode': 'no_proxy'}

class SimpleProxyWrapper(ProxyWrapper):
    """Simple proxy wrapper that just stores configuration"""
    def __init__(self, proxy_url=None):
        logging.info("using SimpleProxyWrapper")
        super().__init__(proxy_url)
        
    @contextmanager
    def proxy_connection(self):
        """Simple context manager that just notifies about proxy intent"""
        logger.info(f"Proxy mode enabled")
        if self.proxy_url:
            logger.info(f"Proxy URL: {self.proxy_url}")
        logger.info("Note: This is a simplified implementation.")
        logger.info("For full proxy functionality, ensure you have the required dependencies installed:")
        logger.info("  pip install requests[socks] pysocks httpx[socks]")
        try:
            yield self
        finally:
            logger.info("Proxy mode disabled")
    
    def get_session(self):
        return requests.Session()
    
    def get_connection_info(self):
        return {'proxy_url': self.proxy_url, 'mode': 'simplified'}

def create_proxy_wrapper(proxy_url=None):
    """Create proxy wrapper based on available dependencies"""
    if not proxy_url:
        return None
        
    try:
        import socks
        from urllib3.contrib.socks import SOCKSProxyManager
        logger.debug("SOCKS dependencies found, using full proxy wrapper")
        return SOCKSProxyWrapper(proxy_url)
    except ImportError as e:
        logger.warning(f"SOCKS dependencies not available: {e}")
        logger.warning("Install with: pip install requests[socks] pysocks httpx[socks]")
        return SimpleProxyWrapper(proxy_url)

def validate_proxy_url(proxy_url):
    """Validate proxy URL format and return None if valid, or an error message if invalid."""
    if not proxy_url:
        return None

    # Parse the URL (add http:// prefix if no scheme is provided)
    if "://" in proxy_url:
        parsed = urlparse(proxy_url)
        if not parsed.scheme:
            return "Proxy URL is missing a scheme (e.g., http:// or socks5://)."
    else:
        parsed = urlparse("http://" + proxy_url)

    # Check supported schemes
    allowed_schemes = {"http", "https", "socks4", "socks5"}
    actual_scheme = parsed.scheme.lower() if parsed.scheme else "http"  # default assumption
    if actual_scheme not in allowed_schemes:
        return f"Unsupported proxy scheme '{parsed.scheme or 'http'}'. Allowed schemes are: http, https, socks4, socks5."

    # Disallow path components (except the empty path after stripping trailing /)
    if parsed.path:
        return "Proxy URL contains an invalid path component. Proxy URLs should not include a path (trailing '/' is allowed and will be ignored)."

    # Require a hostname
    if not parsed.hostname:
        return "Proxy URL is missing a hostname or IP address."

    # Validate port if present
    if parsed.port is not None:
        if not (1 <= parsed.port <= 65535):
            return f"Port number {parsed.port} is invalid. It must be between 1 and 65535."

    # Detect non-numeric port (urlparse sets port=None if non-numeric)
    host_part = parsed.netloc.split("@")[-1]  # after potential auth
    if ":" in host_part and parsed.port is None:
        port_str = host_part.split(":")[1]
        return f"Port must be a numeric value, but '{port_str}' was provided."

    return None  # Valid
