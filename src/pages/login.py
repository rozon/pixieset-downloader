from selenium.common import TimeoutException, ElementClickInterceptedException
from selenium.webdriver.common.by import By
from src.base.decorators import with_webdriver, element
from src.pages.base import BasePage


class LoginPage(BasePage):
    _wait_for = (By.ID, 'GuestLoginForm_email')
    _btn_enter = (By.XPATH, '//input[contains(@id, "SaveButton") and contains(@class, "btn")]')

    @property
    @element
    def input_email(self):
        return self._wait_for

    @property
    @element
    def btn_enter(self):
        return self._btn_enter

    @with_webdriver
    def __init__(self, driver):
        BasePage.__init__(self, driver)
        self.driver = driver

    def perform_login(self):
        try:
            self.input_email.send_keys("random@email.com")
            self.btn_enter.click()
        except TimeoutException:
            print("Pixieset collection not found. Please try again!")
        except ElementClickInterceptedException:
            print("Pixieset collection did not load correctly. Please try again!")
