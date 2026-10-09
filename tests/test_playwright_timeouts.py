from unittest.mock import AsyncMock, Mock, call

import pytest

from recognizer.agents.playwright import async_control, sync_control


def make_challenger(control, challenger_type, browser, scenario):
    """Exercise the real visibility guards without constructing models or a browser."""
    page_type = control.PatchrightPage if browser == "patchright" else control.PlaywrightPage
    timeout_type = control.PatchrightTimeoutError if browser == "patchright" else control.PlaywrightTimeoutError
    page = Mock(spec=page_type)
    label = Mock()
    checkbox = Mock()
    frame = Mock()
    frame.locator.return_value = label
    checkbox_frame = Mock()
    checkbox_frame.first = checkbox_frame
    checkbox_frame.locator.return_value = checkbox
    page.frame_locator.side_effect = lambda selector: checkbox_frame if selector == "iframe[title='reCAPTCHA']" else frame
    method_mock = AsyncMock if control is async_control else Mock
    label.wait_for = method_mock()
    label.is_visible = method_mock(return_value=True)
    checkbox.click = method_mock()
    page.evaluate = method_mock(return_value="")

    if scenario == "timeout":
        label.wait_for.side_effect = [timeout_type("Challenge label wait timed out"), timeout_type("Challenge label wait timed out")]
    elif scenario == "disappeared":
        label.is_visible.side_effect = [True, False]
    elif scenario == "recovered":
        label.wait_for.side_effect = [timeout_type("Challenge label wait timed out"), None]
    else:
        raise ValueError(scenario)

    challenger = object.__new__(challenger_type)
    challenger.page = page
    challenger.retried = 0
    challenger.retry_times = 15
    challenger.captcha_token = None
    return challenger, label, checkbox, timeout_type


@pytest.mark.parametrize("browser", ["playwright", "patchright"])
@pytest.mark.parametrize("scenario", ["timeout", "disappeared"])
def test_sync_invisible_challenge_raises_browser_timeout(browser, scenario):
    challenger, label, checkbox, timeout_type = make_challenger(sync_control, sync_control.SyncChallenger, browser, scenario)

    with pytest.raises(timeout_type, match="reCaptcha Challenge is not visible") as failure:
        challenger.load_captcha()

    assert type(failure.value) is timeout_type
    assert label.wait_for.call_args_list == [call(state="visible", timeout=10000)] * 2
    assert checkbox.click.call_count == (1 if scenario == "timeout" else 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("browser", ["playwright", "patchright"])
@pytest.mark.parametrize("scenario", ["timeout", "disappeared"])
async def test_async_invisible_challenge_raises_browser_timeout(browser, scenario):
    challenger, label, checkbox, timeout_type = make_challenger(async_control, async_control.AsyncChallenger, browser, scenario)

    with pytest.raises(timeout_type, match="reCaptcha Challenge is not visible") as failure:
        await challenger.load_captcha()

    assert type(failure.value) is timeout_type
    assert label.wait_for.await_args_list == [call(state="visible", timeout=10000)] * 2
    assert checkbox.click.await_count == (1 if scenario == "timeout" else 0)


@pytest.mark.parametrize("browser", ["playwright", "patchright"])
def test_sync_challenge_becomes_visible_after_checkbox_click(browser):
    challenger, label, checkbox, _ = make_challenger(sync_control, sync_control.SyncChallenger, browser, "recovered")

    assert challenger.load_captcha() is True
    assert label.wait_for.call_args_list == [call(state="visible", timeout=10000)] * 2
    checkbox.click.assert_called_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize("browser", ["playwright", "patchright"])
async def test_async_challenge_becomes_visible_after_checkbox_click(browser):
    challenger, label, checkbox, _ = make_challenger(async_control, async_control.AsyncChallenger, browser, "recovered")

    assert await challenger.load_captcha() is True
    assert label.wait_for.await_args_list == [call(state="visible", timeout=10000)] * 2
    checkbox.click.assert_awaited_once_with()
