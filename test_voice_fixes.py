import asyncio

from interrupt_detector import InterruptDetector
from kernel import Kernel

detector = InterruptDetector()


def test_month_date():
    assert detector.extract_slots("book a flight on 29 September")["date"] == "29 September"
    assert detector.extract_slots("flight on September 29th")["date"] == "29 September"


def test_devanagari_month_and_words():
    text = detector._normalise_transcript("बुक फ्लाइट फ्रॉम बेंगलुरु टू मुंबई 29 सितंबर")
    slots = detector.extract_slots(text)
    assert slots["origin"] == "Bangalore"
    assert slots["destination"] == "Mumbai"
    assert slots["date"] == "29 September"


def test_short_map_entries_do_not_corrupt_words():
    # "मी" must not be replaced inside "मीटर"
    assert detector._normalise_transcript("मीटर") == "मीटर"


def test_new_delhi_not_split():
    assert detector._find_cities("actually make that new delhi") == ["New Delhi"]


async def test_apply_slots():
    kernel = Kernel()

    t1 = await kernel.apply_slots({"origin": "Bangalore", "destination": "Delhi"})
    assert t1.status.value == "running"

    same = await kernel.apply_slots({"destination": "Delhi"})
    assert same.task_id == t1.task_id  # nothing changed -> same task

    t2 = await kernel.apply_slots({"destination": "Mumbai"})
    assert t2.task_id != t1.task_id
    assert t2.slots == {"origin": "Bangalore", "destination": "Mumbai"}

    t3 = await kernel.apply_slots({"date": "tomorrow", "origin": None})
    assert t3.slots["date"] == "tomorrow"
    assert t3.slots["destination"] == "Mumbai"


async def test_search_cancelled_on_change():
    kernel = Kernel()
    t1 = await kernel.apply_slots({"origin": "Bangalore", "destination": "Delhi"})
    search = asyncio.create_task(
        kernel.run_flight_search_with_retry(t1.task_id, "Bangalore", "Delhi")
    )
    await asyncio.sleep(0.2)
    t2 = await kernel.apply_slots({"destination": "Mumbai"})
    try:
        await search
    except asyncio.CancelledError:
        pass
    assert kernel.current_task_id == t2.task_id
    result = await kernel.run_flight_search_with_retry(t2.task_id, "Bangalore", "Mumbai")
    assert result.success


if __name__ == "__main__":
    test_month_date()
    test_devanagari_month_and_words()
    test_short_map_entries_do_not_corrupt_words()
    test_new_delhi_not_split()
    asyncio.run(test_apply_slots())
    asyncio.run(test_search_cancelled_on_change())
    print("\nALL NEW TESTS PASSED")