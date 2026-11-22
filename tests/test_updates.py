import time

from mihomo_lite.core.state_manager import SettingsStore
from mihomo_lite.core.update_scheduler import UpdateScheduler
from mihomo_lite.models.profile import Profile, ProfileKind


class SyncRunner:
    def submit(self, fn, *, args=(), kwargs=None, on_success=None, on_error=None, on_finished=None):
        try:
            result = fn(*args, **(kwargs or {}))
        except Exception as exc:  # noqa: BLE001 - mirrors TaskRunner
            if on_error:
                on_error(str(exc))
        else:
            if on_success:
                on_success(result)
        finally:
            if on_finished:
                on_finished()


class FakeProfiles:
    def __init__(self, profiles):
        self._profiles = profiles
        self.active_id = profiles[0].id if profiles else ""
        self.calls = []

    @property
    def profiles(self):
        return list(self._profiles)

    def refresh(self, profile_id):
        self.calls.append(profile_id)
        profile = next(p for p in self._profiles if p.id == profile_id)
        profile.updated_at = time.time()
        return profile


def make_profile(kind=ProfileKind.SUBSCRIPTION, age=0.0, url="https://example.test/sub"):
    return Profile(
        id=f"id-{url}",
        name="Sub",
        kind=kind,
        url=url,
        updated_at=time.time() - age,
    )


def make_scheduler(paths, qapp, profiles, *, enabled=True, interval=12):
    settings = SettingsStore(paths)
    settings.load()
    settings.update(
        auto_update_profiles=enabled, auto_update_interval_hours=interval
    )
    scheduler = UpdateScheduler(settings, profiles, SyncRunner())
    return scheduler, settings


def test_due_profiles_only_includes_stale_subscriptions(paths, qapp):
    fresh = make_profile(age=60, url="https://a")
    stale = make_profile(age=13 * 3600, url="https://b")
    local = make_profile(kind=ProfileKind.LOCAL, age=13 * 3600, url="")
    scheduler, _ = make_scheduler(paths, qapp, FakeProfiles([fresh, stale, local]))

    due = scheduler.due_profiles()
    assert [p.id for p in due] == [stale.id]


def test_force_includes_fresh_subscriptions(paths, qapp):
    fresh = make_profile(age=0)
    scheduler, _ = make_scheduler(paths, qapp, FakeProfiles([fresh]))
    assert scheduler.due_profiles(force=True) == [fresh]


def test_update_all_is_skipped_when_disabled(paths, qapp):
    profiles = FakeProfiles([make_profile(age=0)])
    scheduler, _ = make_scheduler(paths, qapp, profiles, enabled=False)
    assert scheduler.update_all() is False
    assert profiles.calls == []


def test_update_all_refreshes_due_profiles(paths, qapp):
    profiles = FakeProfiles([make_profile(age=99 * 3600)])
    scheduler, _ = make_scheduler(paths, qapp, profiles)
    results = []
    scheduler.finished.connect(lambda updated, failed: results.append((updated, failed)))

    assert scheduler.update_all() is True
    assert profiles.calls == [profiles.profiles[0].id]
    assert results == [(1, 0)]


def test_failed_update_is_reported_and_does_not_block_the_queue(paths, qapp):
    first = make_profile(age=99 * 3600, url="https://bad")
    second = make_profile(age=99 * 3600, url="https://good")

    class FailingProfiles(FakeProfiles):
        def refresh(self, profile_id):
            if profile_id == first.id:
                self.calls.append(profile_id)
                raise RuntimeError("download failed")
            return super().refresh(profile_id)

    profiles = FailingProfiles([first, second])
    scheduler, _ = make_scheduler(paths, qapp, profiles)
    failures = []
    results = []
    scheduler.profile_failed.connect(lambda name, msg: failures.append((name, msg)))
    scheduler.finished.connect(lambda u, f: results.append((u, f)))

    assert scheduler.update_all(force=True) is True
    assert failures and "download failed" in failures[0][1]
    assert results == [(1, 1)]
    assert second.id in profiles.calls


def test_busy_scheduler_rejects_a_second_run(paths, qapp):
    profiles = FakeProfiles([make_profile(age=99 * 3600)])
    scheduler, _ = make_scheduler(paths, qapp, profiles)

    class SlowProfiles(FakeProfiles):
        def refresh(self, profile_id):
            assert scheduler.update_all(force=True) is False
            return super().refresh(profile_id)

    profiles.__class__ = SlowProfiles
    assert scheduler.update_all(force=True) is True


def test_active_profile_update_is_announced(paths, qapp):
    profile = make_profile(age=99 * 3600)
    profiles = FakeProfiles([profile])
    scheduler, _ = make_scheduler(paths, qapp, profiles)
    announced = []
    scheduler.active_profile_updated.connect(lambda p: announced.append(p.id))

    scheduler.update_all(force=True)
    assert announced == [profile.id]
