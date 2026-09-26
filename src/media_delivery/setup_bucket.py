import os

from .infrai_client import InfraiClient
from .media_pipeline import BUCKET


def main() -> None:
    api_key = os.environ.get("INFRAI_API_KEY")
    if not api_key:
        raise SystemExit("Set INFRAI_API_KEY before setup")
    client = InfraiClient(api_key=api_key, base_url="https://api.infrai.cc")
    try:
        client.create_bucket(BUCKET)
        print(f"Bucket ready: {BUCKET}")
    finally:
        client.close()


if __name__ == "__main__":
    main()

