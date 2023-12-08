from selenium.webdriver.common.by import By
from src.base.decorators import with_webdriver, element
from src.pages.base import BasePage


class CardElement(BasePage):
    _wait_for = (By.XPATH, '//div[@class="rsSlide "]')
    _btn_dismiss = (By.XPATH, '//a[contains(@class, "slide-dismiss")]')

    @property
    @element
    def input_email(self):
        return self._wait_for

    @property
    @element
    def btn_dismiss(self):
        return self._btn_dismiss

    @with_webdriver
    def __init__(self, driver):
        BasePage.__init__(self, driver)
        self.driver = driver

    def dismiss(self):
        self.btn_dismiss.click()
