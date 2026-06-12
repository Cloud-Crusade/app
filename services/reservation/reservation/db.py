from collections.abc import AsyncIterator

from common.db import NAMING_CONVENTION, buildEngine
from config.settings import settings
from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

writerEngine = buildEngine(settings.db_writer_url)
readerEngine = buildEngine(settings.db_reader_url)
writerFactory = async_sessionmaker(writerEngine, expire_on_commit=False, class_=AsyncSession)
readerFactory = async_sessionmaker(readerEngine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


async def getWriterSession() -> AsyncIterator[AsyncSession]:
    async with writerFactory() as session:
        yield session


async def getReaderSession() -> AsyncIterator[AsyncSession]:
    async with readerFactory() as session:
        yield session
