import pytest


@pytest.mark.usefixtures("driver", "login", "card", "gallery")
class TestDownload:

    def test_download_all_photos(self, login, card, gallery):
        login.wait_for().perform_login()
        card.wait_for().dismiss()
        gallery.wait_for().load().download()
