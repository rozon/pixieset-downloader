from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.wait import WebDriverWait
from src.base.driver import Driver
from src.base.web_element import WebElement


def with_webdriver(func):
    def wrapper(self, *args, **kwargs):
        return func(self, Driver, *args, **kwargs)

    return wrapper


def element(func):
    def wrapper(*args, **kwargs):
        try:
            locator = func(*args, **kwargs)
            _element = WebDriverWait(Driver.driver, Driver.wait_timeout).until(
                expected_conditions.visibility_of_element_located(locator))
            return WebElement(_element)
        except Exception as e:
            raise e

    return wrapper


def elements(func):
    def wrapper(*args, **kwargs):
        try:
            locator = func(*args, **kwargs)
            _elements = WebDriverWait(Driver.driver, Driver.wait_timeout).until(
                expected_conditions.visibility_of_any_elements_located(locator))
            _list = []
            for _element in _elements:
                _list.append(WebElement(_element))
            return _list
        except Exception as e:
            raise e

    return wrapper


def wait_for(func):
    def wrapper(self, *args, **kwargs):
        _wait_for = self._wait_for
        try:
            WebDriverWait(Driver.driver, Driver.wait_timeout).until(
                expected_conditions.visibility_of_element_located(_wait_for))
        except Exception as e:
            raise e
        return func(self, *args, **kwargs)
    return wrapper
