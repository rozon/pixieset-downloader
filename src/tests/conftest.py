from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options
from webdriver_manager.firefox import GeckoDriverManager
from src.base.driver import Driver
from src.pages.login import LoginPage
from src.pages.card import CardElement
from src.pages.gallery import GalleryPage
import pytest
import os

load_dotenv()


@pytest.fixture(scope="class")
def driver(request):
    options = Options()
    options.add_argument("--headless")
    options.add_argument('--disable-gpu')
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    driver = webdriver.Firefox(service=FirefoxService(GeckoDriverManager().install()), options=options)
    driver.maximize_window()

    url = os.getenv("PIXIESET_COLLECTION_URL")

    if url:
        driver.get(url)
    else:
        raise ValueError("Invalid or unspecified PIXIESET_COLLECTION_URL")

    Driver.initialize(driver)
    request.cls.driver = driver

    yield driver
    Driver.quit()


@pytest.fixture(scope="class")
def login():
    return LoginPage()


@pytest.fixture(scope="class")
def card():
    return CardElement()


@pytest.fixture(scope="class")
def gallery():
    return GalleryPage()
