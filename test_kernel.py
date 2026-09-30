import asyncio

from kernel import Kernel


async def test_normal_flight():

    print("\n==============================")
    print("TEST 1: NORMAL + RETRY")
    print("==============================")

    kernel = Kernel()

    task = kernel.start_task(
        "Find a flight from Bangalore to Delhi",
        slots={
            "origin": "Bangalore",
            "destination": "Delhi"
        }
    )

    result = await kernel.run_flight_search_with_retry(
        task.task_id,
        "Bangalore",
        "Delhi"
    )

    assert result.success
    assert task.status.value == "done"

    print("PASS")


async def test_correction():

    print("\n==============================")
    print("TEST 2: INTERRUPTION + CORRECTION")
    print("==============================")

    kernel = Kernel()

    kernel.handle_user_input(
        "Find a flight from Bangalore to Delhi"
    )

    kernel.start_task(
        "Find a flight from Bangalore to Delhi",
        slots={
            "origin": "Bangalore",
            "destination": "Delhi"
        }
    )

    new_task = await kernel.handle_user_correction(
        "Actually, make that Mumbai"
    )

    assert new_task.slots["origin"] == "Bangalore"
    assert new_task.slots["destination"] == "Mumbai"

    assert new_task.status.value == "running"

    print("PASS")


async def test_late_result():

    print("\n==============================")
    print("TEST 3: LATE RESULT")
    print("==============================")

    kernel = Kernel()

    task_a = kernel.start_task(
        "Find a flight from Bangalore to Delhi"
    )

    slow_task = asyncio.create_task(
        kernel.slow_async_task(task_a.task_id)
    )

    await asyncio.sleep(0.1)

    await kernel.cancel_current_task()

    task_b = kernel.start_task(
        "Find a flight from Bangalore to Mumbai"
    )

    late_result = await slow_task

    accepted = kernel.complete_task(
        late_result["task_id"],
        late_result["result_id"]
    )

    assert accepted is False
    assert kernel.current_task_id == task_b.task_id

    print("PASS")


async def test_duplicate_result():

    print("\n==============================")
    print("TEST 4: DUPLICATE RESULT")
    print("==============================")

    kernel = Kernel()

    task = kernel.start_task(
        "Find a flight from Bangalore to Delhi"
    )

    result_id = "result-123"

    first = kernel.complete_task(
        task.task_id,
        result_id
    )

    second = kernel.complete_task(
        task.task_id,
        result_id
    )

    assert first is True
    assert second is False

    print("PASS")


async def main():

    await test_normal_flight()
    await test_correction()
    await test_late_result()
    await test_duplicate_result()

    print("\n================================")
    print("ALL KERNEL TESTS PASSED")
    print("================================")


if __name__ == "__main__":
    asyncio.run(main())