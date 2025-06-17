import asyncio
import logging
from pathlib import Path
from typing import Union

from telegram import Bot, InputFile

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.DEBUG
)


async def send_with_ptb(
    token: str,
    base_url: str,
    chat_id: Union[str, int],
    filename: str,
    file_path: Path,
    kwargs: dict[str, Union[str, bool]],
    timeout: int,
):
    async with Bot(
        token=token,
        base_url=base_url,
    ) as bot:
        await bot.send_document(
            chat_id=chat_id,
            document=InputFile(
                obj=file_path.open("rb"), filename=filename, attach=True, read_file_handle=False
            ),
            filename=filename,
            read_timeout=timeout,
            write_timeout=timeout,
            connect_timeout=timeout,
            **kwargs,
        )


async def main():
    token = "5995725266:AAG1yDLgNJK9Ib9Mw4yHQs9qv0pofZTi_Og"
    chat_id = 371607266
    file_path = Path("docker_txttg/近代中国史料丛刊三辑_0491_500_两广官报_两广官报编辑所辑.pdf")
    filename = "近代中国史料丛刊三辑_0491_500_两广官报_两广官报编辑所辑.pdf"
    kwargs = {
        "caption": "caption",
        "disable_content_type_detection": True,
        "disable_notification": True,
    }
    base_url = "http://195.245.229.194:8081/bot"
    timeout = 1800

    for callback in (
        send_with_ptb,
    ):
        try:
            await callback(
                timeout=timeout,
                base_url=base_url,
                token=token,
                chat_id=chat_id,
                filename=filename,
                file_path=file_path,
                kwargs=kwargs,
            )
        except Exception as exc:
            print(f"{callback.__name__} failed: {exc}")


if __name__ == "__main__":
    asyncio.run(main())