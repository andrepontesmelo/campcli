from campcli import command_router


class TestDispatch:
    def test_verbose_on(self, poller):
        reply = command_router.dispatch("/verbose on", poller)
        assert reply == "verbose logging ON"
        assert poller._verbose is True

    def test_verbose_off(self, poller):
        poller.set_verbose(True)
        reply = command_router.dispatch("/verbose off", poller)
        assert reply == "verbose logging OFF"
        assert poller._verbose is False

    def test_unknown_command_returns_none(self, poller):
        reply = command_router.dispatch("garbage", poller)
        assert reply is None

    def test_whitespace_around_command(self, poller):
        reply = command_router.dispatch("  /verbose on  ", poller)
        assert reply == "verbose logging ON"
