import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from recruitment_system.config import env_flag


class ConfigTest(unittest.TestCase):
    def test_env_flag_loads_dotenv_file(self) -> None:
        previous = os.environ.pop("ENABLE_LLM", None)
        try:
            with TemporaryDirectory() as temp_dir:
                dotenv_path = Path(temp_dir) / ".env"
                dotenv_path.write_text("ENABLE_LLM=true\n", encoding="utf-8")

                self.assertTrue(env_flag("ENABLE_LLM", False, dotenv_path=dotenv_path))
        finally:
            if previous is not None:
                os.environ["ENABLE_LLM"] = previous


if __name__ == "__main__":
    unittest.main()
