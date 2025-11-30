from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from webdriver_manager.firefox import GeckoDriverManager

def get_driver():
    """Create a stable Firefox driver with optimized options"""
    firefox_options = Options()
    
    # Optional: Run headless (no browser window)
    # firefox_options.add_argument("--headless")
    
    # Stability and privacy options
    firefox_options.set_preference("dom.webdriver.enabled", False)
    firefox_options.set_preference('useAutomationExtension', False)
    
    # Disable cache for fresh data
    firefox_options.set_preference("browser.cache.disk.enable", False)
    firefox_options.set_preference("browser.cache.memory.enable", False)
    firefox_options.set_preference("browser.cache.offline.enable", False)
    firefox_options.set_preference("network.http.use-cache", False)
    
    # Performance settings
    firefox_options.set_preference("browser.download.folderList", 2)
    firefox_options.set_preference("browser.helperApps.neverAsk.saveToDisk", "application/octet-stream")
    
    # Logging
    firefox_options.set_preference("devtools.console.stdout.content", False)
    
    # Create driver with webdriver-manager (auto-downloads geckodriver)
    driver = webdriver.Firefox(
        service=Service(GeckoDriverManager().install()),
        options=firefox_options
    )
    
    # Set timeouts
    driver.set_page_load_timeout(30)
    driver.implicitly_wait(10)
    
    return driver