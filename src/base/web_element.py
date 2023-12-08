from src.base.driver import Driver


class WebElement(object):
    web_element = None

    def __init__(self, web_element):
        self.web_element = web_element

    def click(self):
        Driver.driver.execute_script(
            "arguments[0].scrollIntoView();", self.web_element)
        self.web_element.click()

    def is_displayed(self):
        return self.web_element.is_displayed()

    def send_keys(self, keys):
        self.web_element.send_keys(keys)

    def get_attribute(self, value):
        return self.web_element.get_attribute(value)
