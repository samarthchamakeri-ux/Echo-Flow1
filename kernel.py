
import asyncio
import json
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from flight_search import FlightSearchTool
from interrupt_detector import InterruptDetector


# ============================================================
# TASK STATE
# ============================================================

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class Task:
    task_id: str
    goal: str
    status: TaskStatus = TaskStatus.PENDING

    current_step: int = 0
    checkpoint: dict[str, Any] = field(default_factory=dict)

    retry_count: int = 0

    # Information collected from the user
    slots: dict[str, Any] = field(default_factory=dict)


def create_task(goal: str) -> Task:
    return Task(
        task_id=str(uuid.uuid4()),
        goal=goal,
    )


# ============================================================
# KERNEL
# ============================================================

class Kernel:

    def __init__(self):

        self.current_task: Task | None = None
        self.current_task_id: str | None = None

        self._current_async_task: asyncio.Task | None = None

        self.processed_results: set[str] = set()

        self.max_retries = 3

        self.flight_tool = FlightSearchTool()

        self.interrupt_detector = InterruptDetector()

        self.previous_user_text = ""

    # ========================================================
    # HANDLE FIRST USER INPUT
    # ========================================================

    def handle_user_input(self, transcript: str):

        result = self.interrupt_detector.classify_interruption(
            transcript,
            current_slots={},
        )

        print("\n--- Interruption Detection ---")
        print(f"Type: {result.interruption_type}")
        print(f"Interrupted: {result.interrupted}")
        print(f"Changed slots: {result.changed_slots}")
        print(f"New goal: {result.new_goal}")

        self.previous_user_text = transcript

        return result

    # ========================================================
    # TASK CREATION
    # ========================================================

    def start_task(
        self,
        goal: str,
        slots: dict[str, Any] | None = None,
    ) -> Task:

        task = create_task(goal)

        if slots:
            task.slots = dict(slots)

        task.status = TaskStatus.RUNNING

        self.current_task = task
        self.current_task_id = task.task_id

        print("\n================================")
        print("NEW TASK")
        print("================================")
        print("Task ID:", task.task_id)
        print("Goal:", task.goal)
        print("Slots:", task.slots)

        return task

    # ========================================================
    # HANDLE USER CORRECTION / CONSTRAINT
    # ========================================================

    async def handle_user_correction(
        self,
        transcript: str,
    ):

        # If there is no active task, treat this
        # as a normal first request.
        if self.current_task is None:
            return self.handle_user_input(transcript)

        old_task = self.current_task

        # Detect changes against the existing slots.
        result = self.interrupt_detector.classify_interruption(
            transcript,
            current_slots=old_task.slots,
        )

        print("\n--- Interruption Detection ---")
        print(f"Type: {result.interruption_type}")
        print(f"Interrupted: {result.interrupted}")
        print(f"Changed slots: {result.changed_slots}")
        print(f"New goal: {result.new_goal}")

        # Nothing useful was extracted.
        if not result.changed_slots:
            return result

        # ====================================================
        # MERGE OLD + NEW SLOTS
        # ====================================================

        new_slots = dict(old_task.slots)

        new_slots.update(
            result.changed_slots
        )

        print("\nPreserved slots:")
        print(old_task.slots)

        print("\nUpdated slots:")
        print(new_slots)

        # ====================================================
        # BUILD UPDATED GOAL
        # ====================================================

        new_goal = self._build_goal_from_slots(
            fallback_goal=old_task.goal,
            slots=new_slots,
        )

        print("\nUpdated goal:")
        print(new_goal)

        # ====================================================
        # CANCEL OLD TASK
        # ====================================================

        await self.cancel_current_task()

        # ====================================================
        # CREATE UPDATED TASK
        # ====================================================

        new_task = self.start_task(
            goal=new_goal,
            slots=new_slots,
        )

        return result

    # ========================================================
    # BUILD GOAL FROM ALL CURRENT CONTEXT
    # ========================================================

    def _build_goal_from_slots(
        self,
        fallback_goal: str,
        slots: dict[str, Any],
    ) -> str:

        origin = slots.get("origin")
        destination = slots.get("destination")
        date = slots.get("date")
        time = slots.get("time")
        passengers = slots.get("passengers")
        trip_type = slots.get("trip_type")

        # We need origin + destination to build
        # a complete flight goal.
        if not origin or not destination:
            return fallback_goal

        goal = (
            f"Find a flight from "
            f"{origin} to {destination}"
        )

        if date:
            goal += f" on {date}"

        if time:
            goal += f" at {time}"

        if passengers:
            goal += (
                f" for {passengers} passenger"
            )

            if str(passengers) != "1":
                goal += "s"

        if trip_type:
            goal += f" ({trip_type} trip)"

        return goal

    # ========================================================
    # COMPLETE TASK
    # ========================================================

    def complete_task(
        self,
        task_id: str,
        result_id: str,
    ):

        if self.current_task is None:
            print("Ignoring result: no current task.")
            return False

        if task_id != self.current_task_id:
            print("Ignoring result from old task.")
            return False

        if result_id in self.processed_results:
            print("Ignoring duplicate result.")
            return False

        self.processed_results.add(result_id)

        self.current_task.status = TaskStatus.DONE

        print("\nTask completed.")
        print("Task ID:", task_id)

        self.clear_checkpoint()

        return True

    # ========================================================
    # FAIL TASK
    # ========================================================

    def fail_task(
        self,
        task_id: str,
    ):

        if self.current_task is None:
            print("Cannot fail task: no current task.")
            return False

        if task_id != self.current_task_id:
            print("Cannot fail old task.")
            return False

        self.current_task.status = TaskStatus.FAILED

        print("\nTask failed.")
        print("Task ID:", task_id)

        return True

    # ========================================================
    # RETRY TASK
    # ========================================================

    def retry_task(
        self,
        task_id: str,
    ):

        if self.current_task is None:
            print("Cannot retry: no current task.")
            return False

        if task_id != self.current_task_id:
            print("Cannot retry old task.")
            return False

        if self.current_task.status != TaskStatus.FAILED:
            print("Task is not failed.")
            return False

        if self.current_task.retry_count >= self.max_retries:
            print("Maximum retry limit reached.")
            return False

        self.current_task.retry_count += 1

        self.current_task.status = TaskStatus.RUNNING

        print(
            f"\nRetrying task "
            f"(attempt {self.current_task.retry_count + 1})"
        )

        return True

    # ========================================================
    # ASYNC DUMMY TASK
    # ========================================================

    async def run_async_task(
        self,
        task_id: str,
    ):

        try:

            for i in range(10):

                if self.current_task_id != task_id:
                    print("Async task became stale.")
                    return

                print(f"{i + 1} seconds...")

                await asyncio.sleep(1)

        except asyncio.CancelledError:

            print(
                f"Async task {task_id} "
                f"was cancelled."
            )

            raise

    # ========================================================
    # START ASYNC TASK
    # ========================================================

    def start_async_task(
        self,
        task_id: str,
    ):

        self._current_async_task = asyncio.create_task(
            self.run_async_task(task_id)
        )

        print("Async task created.")

        return self._current_async_task

    # ========================================================
    # SAFE ASYNC CANCELLATION
    # ========================================================

    async def cancel_current_task(self):

        if self.current_task is None:
            print("No current task to cancel.")
            return False

        task_id = self.current_task_id

        print("\nCancelling task:", task_id)

        self.current_task.status = TaskStatus.CANCELLED

        async_task = self._current_async_task

        if async_task is not None:

            if not async_task.done():

                async_task.cancel()

                try:
                    await async_task

                except asyncio.CancelledError:

                    print(
                        f"Async task {task_id} "
                        f"was cancelled."
                    )

                print(
                    "Async task cancellation confirmed."
                )

        self.current_task = None
        self.current_task_id = None
        self._current_async_task = None

        return True

    # ========================================================
    # SLOW TASK - USED FOR LATE RESULT TEST
    # ========================================================

    async def slow_async_task(
        self,
        task_id: str,
    ):

        try:

            await asyncio.sleep(5)

            return {
                "task_id": task_id,
                "result_id": str(uuid.uuid4()),
                "message": "Slow result",
            }

        except asyncio.CancelledError:

            return {
                "task_id": task_id,
                "result_id": str(uuid.uuid4()),
                "message": "Late result",
            }

    # ========================================================
    # CHECKPOINT
    # ========================================================

    def save_checkpoint(
        self,
        task_id: str,
        step: int,
        data: dict[str, Any],
    ):

        if self.current_task is None:
            print("Cannot save checkpoint.")
            return False

        if task_id != self.current_task_id:
            print("Cannot save checkpoint for old task.")
            return False

        self.current_task.current_step = step
        self.current_task.checkpoint = data

        checkpoint_data = {
            "task_id": task_id,
            "goal": self.current_task.goal,
            "current_step": step,
            "checkpoint": data,
            "slots": self.current_task.slots,
            "retry_count": self.current_task.retry_count,
        }

        with open(
            "checkpoint.json",
            "w",
        ) as file:

            json.dump(
                checkpoint_data,
                file,
                indent=4,
            )

        print("\nCheckpoint saved.")
        print("Step:", step)
        print("Data:", data)

        return True

    # ========================================================
    # LOAD CHECKPOINT
    # ========================================================

    def load_checkpoint(self):

        try:

            with open(
                "checkpoint.json",
                "r",
            ) as file:

                data = json.load(file)

            print("\nCheckpoint loaded.")

            return data

        except FileNotFoundError:

            print("\nNo checkpoint found.")

            return None

    # ========================================================
    # RESUME TASK
    # ========================================================

    def resume_task(
        self,
        task_id: str,
    ):

        if self.current_task is None:
            print("No current task.")
            return None

        if task_id != self.current_task_id:
            print("Cannot resume old task.")
            return None

        self.current_task.status = TaskStatus.RUNNING

        print(
            f"\nResuming task {task_id} "
            f"from step "
            f"{self.current_task.current_step}."
        )

        print(
            "Checkpoint:",
            self.current_task.checkpoint,
        )

        return self.current_task

    # ========================================================
    # GET RESUME POINT
    # ========================================================

    def get_resume_point(
        self,
        task_id: str,
    ):

        if self.current_task is None:
            return None

        if task_id != self.current_task_id:
            return None

        return {
            "step": self.current_task.current_step,
            "checkpoint": self.current_task.checkpoint,
        }

    # ========================================================
    # RESTORE TASK FROM DISK
    # ========================================================

    def restore_task(self):

        data = self.load_checkpoint()

        if data is None:
            return None

        task = Task(
            task_id=data["task_id"],
            goal=data["goal"],
            status=TaskStatus.RUNNING,
            current_step=data["current_step"],
            checkpoint=data["checkpoint"],
            retry_count=data.get(
                "retry_count",
                0,
            ),
            slots=data.get(
                "slots",
                {},
            ),
        )

        self.current_task = task
        self.current_task_id = task.task_id

        print("\nTask restored.")
        print("Task ID:", task.task_id)
        print("Goal:", task.goal)
        print("Step:", task.current_step)
        print("Slots:", task.slots)

        return task

    # ========================================================
    # CLEAR CHECKPOINT
    # ========================================================

    def clear_checkpoint(self):

        try:

            import os

            if os.path.exists(
                "checkpoint.json"
            ):

                os.remove(
                    "checkpoint.json"
                )

                print("Checkpoint cleared.")

        except Exception as e:

            print(
                "Could not clear checkpoint:",
                e,
            )

    # ========================================================
    # PERSON C - FLIGHT SEARCH
    # ========================================================

    async def run_flight_search(
        self,
        task_id: str,
        origin: str,
        destination: str,
    ):

        return await self.flight_tool.run(
            task_id=task_id,
            origin=origin,
            destination=destination,
        )

    # ========================================================
    # FLIGHT SEARCH + RETRY + OWNERSHIP CHECK
    # ========================================================

    async def run_flight_search_with_retry(
        self,
        task_id: str,
        origin: str,
        destination: str,
    ):

        while True:

            # ----------------------------------------------
            # OWNERSHIP CHECK
            # ----------------------------------------------

            if self.current_task is None:

                print(
                    "Search stopped: "
                    "no current task."
                )

                return None

            if self.current_task_id != task_id:

                print(
                    "Search stopped: "
                    "task is stale."
                )

                return None

            if self.current_task.status != TaskStatus.RUNNING:

                print(
                    "Search stopped: "
                    "task is not running."
                )

                return None

            # ----------------------------------------------
            # START SEARCH
            # ----------------------------------------------

            self._current_async_task = (
                asyncio.create_task(
                    self.run_flight_search(
                        task_id,
                        origin,
                        destination,
                    )
                )
            )

            try:

                result = await self._current_async_task

            except asyncio.CancelledError:

                print(
                    f"Flight search task "
                    f"{task_id} cancelled."
                )

                raise

            finally:

                self._current_async_task = None

            # ----------------------------------------------
            # CHECK TASK OWNERSHIP AGAIN
            # ----------------------------------------------

            if self.current_task is None:

                print(
                    "Ignoring flight result: "
                    "no current task."
                )

                return None

            if self.current_task_id != task_id:

                print(
                    "Ignoring flight result "
                    "from old task."
                )

                return None

            if self.current_task.status != TaskStatus.RUNNING:

                print(
                    "Ignoring flight result: "
                    "task is no longer running."
                )

                return None

            # ----------------------------------------------
            # SUCCESS
            # ----------------------------------------------

            if result.success:

                result_id = str(uuid.uuid4())

                self.complete_task(
                    task_id,
                    result_id,
                )

                print(
                    "\nFlight search result:"
                )

                print(result.data)

                return result

            # ----------------------------------------------
            # NON-RETRYABLE ERROR
            # ----------------------------------------------

            if not result.retryable:

                self.fail_task(task_id)

                print(
                    "Non-retryable error:",
                    result.error,
                )

                return result

            # ----------------------------------------------
            # MAX RETRIES
            # ----------------------------------------------

            if (
                self.current_task.retry_count
                >= self.max_retries
            ):

                self.fail_task(task_id)

                print(
                    "Retry limit reached:",
                    result.error,
                )

                return result

            # ----------------------------------------------
            # RETRY
            # ----------------------------------------------

            self.fail_task(task_id)

            if not self.retry_task(task_id):
                return result

            print(
                "\nRetrying flight search..."
            )


# ============================================================
# TEST
# ============================================================

async def main():

    kernel = Kernel()

    task = kernel.start_task(
        "Find a flight from Bangalore to Delhi",
        slots={
            "origin": "Bangalore",
            "destination": "Delhi",
        },
    )

    print(
        "\nCompleting task with first result..."
    )

    result_id = "result-123"

    first = kernel.complete_task(
        task.task_id,
        result_id,
    )

    print(
        "First result accepted:",
        first,
    )

    print(
        "\nSending the SAME result again..."
    )

    second = kernel.complete_task(
        task.task_id,
        result_id,
    )

    print(
        "Duplicate result accepted:",
        second,
    )

    print("\n--- FINAL STATE ---")

    print(
        "Status:",
        task.status.value,
    )


if __name__ == "__main__":
    asyncio.run(main())

