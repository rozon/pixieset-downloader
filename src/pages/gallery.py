from selenium.common import TimeoutException
from selenium.webdriver.common.by import By
from src.base.decorators import with_webdriver, element, elements
from src.base.driver import Driver
from src.pages.base import BasePage
import requests
import os
import re


class GalleryPage(BasePage):
    _wait_for = (By.ID, 'gamma-container')
    _btn_back_top = (By.XPATH, '//div[@id="back-top-btn"]/div/a')
    _images = (By.XPATH, '//ul/li/img')

    @property
    @element
    def btn_back_top(self):
        return self._btn_back_top

    @property
    @elements
    def images(self):
        return self._images

    @with_webdriver
    def __init__(self, driver):
        BasePage.__init__(self, driver)
        self.driver = driver

    def load(self):
        print("\n")
        while True:
            try:
                if self.btn_back_top.is_displayed():
                    break
            except TimeoutException:
                print("Waiting for the entire gallery to load...")
            Driver.driver.execute_script("window.scrollBy(0, 500);")
        return self

    def _get_sources(self):
        sources = {}
        pattern = r'(-)(medium|large|xlarge)\b'
        for image in self.images:
            src = re.sub(pattern, '-xxlarge', image.get_attribute("src"))
            sources[image.get_attribute("alt")] = src
        return sources

    def download(self):
        sources = self._get_sources()
        if not os.path.exists(os.getenv("DOWNLOAD_DIRECTORY")):
            os.makedirs(os.getenv("DOWNLOAD_DIRECTORY"))

        for alt, src in sources.items():
            try:
                response = requests.get(src)
                if response.status_code == 200:
                    image_name = alt
                    image_path = os.path.join(os.getenv("DOWNLOAD_DIRECTORY"), image_name)
                    with open(image_path, "wb") as image_file:
                        image_file.write(response.content)
                    print(f"Downloaded {image_name} successfully.")
                else:
                    print(f"Failed to download {src}: Status code {response.status_code}")
            except Exception as e:
                print(f"Failed to download {src}: {e}")
        print("Done!")
