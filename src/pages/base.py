from src.base.decorators import wait_for


class BasePage(object):

    def __init__(self, driver):
        self.driver = driver

    @wait_for
    def wait_for(self):
        return self
