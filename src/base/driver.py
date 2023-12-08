class Driver(object):
    driver = None
    wait_timeout = None

    @classmethod
    def initialize(cls, driver):
        cls.driver = driver
        cls.wait_timeout = 8

    @classmethod
    def quit(cls):
        if cls.driver:
            cls.driver.quit()
