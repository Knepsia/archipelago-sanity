import base64
import enum
import os
import pathlib
from typing import Optional, Union

from .ips import patch


class RomWriterType(enum.IntEnum):
    null = 0
    file = 1
    ipsblob = 2
    base64 = 3


class RomWriter:
    romWriterType: RomWriterType
    romData: bytearray
    ipsBlob: bytearray
    baseFileName: str

    def __init__(self) -> None:
        self.romWriterType = RomWriterType.null
        self.rom_data = bytearray()
        self.ipsblob = bytearray()
        self.baseFilename = ''

    @classmethod
    def fromFilePath(cls, origRomPath: str) -> "RomWriter":
        instance = cls()
        instance.romWriterType = RomWriterType.file
        instance.rom_data = RomWriter.createWorkingFileCopy(origRomPath)
        instance.patch_if_vanilla()
        return instance

    @classmethod
    def fromBlankIps(cls) -> "RomWriter":
        instance = cls()
        instance.romWriterType = RomWriterType.ipsblob
        instance.ipsblob = bytearray(b'PATCH')
        return instance

    @classmethod
    def fromBase64(cls, b64str: Union[str, bytes]) -> "RomWriter":
        instance = cls()
        instance.romWriterType = RomWriterType.base64
        instance.rom_data = bytearray(base64.decodebytes(b64str.encode() if isinstance(b64str, str) else b64str))
        return instance

    @staticmethod
    def index_to_snes_addr(i: int) -> int:
        """ converts a PC rom offset to a SNES lorom address """
        a = ((i << 1) & 0x7f0000) + 0x800000
        b = (i & 0x7fff) + 0x8000
        snes = a | b
        return snes

    @staticmethod
    def snes_to_index_addr(addr: int) -> int:
        """ converts a SNES lorom address to a PC rom offset """
        pc = ((addr & 0x7f0000) >> 1) | (addr & 0x7fff)
        return pc

    @staticmethod
    def createWorkingFileCopy(origFile: str) -> bytearray:
        if not os.path.exists(origFile):
            raise Exception(f'origFile not found: {origFile}')
        with open(origFile, 'rb') as orig:
            return bytearray(orig.read())

    @staticmethod
    def isAllRepeatedBytes(data: bytes) -> bool:
        if len(data) < 2:
            return False
        byte = data[0]
        for i in range(1, len(data)):
            if data[i] != byte:
                return False
        return True

    def writeBytes(self, address: int, data: bytes) -> None:
        if self.romWriterType in {RomWriterType.file, RomWriterType.base64}:
            assert len(self.rom_data) >= address + len(data)
            self.rom_data[address:address + len(data)] = data
        elif self.romWriterType == RomWriterType.ipsblob:
            if len(data) >= 65536:
                raise Exception(f'data length {len(data)} exceeds max IPS len of 65536')
            self.ipsblob.extend(address.to_bytes(3, 'big'))
            if len(data) > 10 and RomWriter.isAllRepeatedBytes(data):
                # RLE encode
                self.ipsblob.extend(b'\x00\x00')
                self.ipsblob.extend(len(data).to_bytes(2, 'big'))
                self.ipsblob.append(data[0])
            else:
                # normal patch data
                self.ipsblob.extend(len(data).to_bytes(2, 'big'))
                self.ipsblob.extend(data)
        else:
            raise ValueError(f"invalid rom writer type: {self.romWriterType}")

    def writeItem(self, address: int, plmid: bytes, ammoAmount: bytes = b"\x00") -> None:
        if len(plmid) != 2 or len(ammoAmount) != 1:
            raise Exception(f'plmid length ({len(plmid)}) must be 2 and ammoAmount '
                            f'length ({len(ammoAmount)}) must be 1')
        self.writeBytes(address, plmid)
        self.writeBytes(address + 5, ammoAmount)

    def finalizeRom(self, filename: Optional[str] = None) -> None:
        if self.romWriterType == RomWriterType.file:
            assert filename
            with open(filename, "wb") as file:
                file.write(self.rom_data)
        elif self.romWriterType == RomWriterType.ipsblob:
            self.ipsblob.extend(b'EOF')
        elif self.romWriterType == RomWriterType.base64:
            pass

    def getFinalIps(self) -> bytearray:
        if self.romWriterType != RomWriterType.ipsblob:
            raise Exception('getFinalIps() called on non-ipsblob-typed RomWriter')
        if bytes(self.ipsblob[-3:]) != b'EOF':
            raise Exception('getFinalIps() called before finalizeRom()')
        return self.ipsblob

    def getBase64RomData(self) -> bytes:
        if self.romWriterType == RomWriterType.ipsblob:
            raise ValueError('getBase64RomData() called on ipsblob-typed RomWriter')
        return base64.encodebytes(self.rom_data)

    def setBaseFilename(self, baseFilename: str) -> None:
        self.baseFilename = baseFilename

    def getBaseFilename(self) -> str:
        return self.baseFilename

    def patch_if_vanilla(self) -> None:
        if len(self.rom_data) != 4194304:  # subversion rom
            if len(self.rom_data) == 3145728:  # vanilla SM
                patch_path = pathlib.Path(__file__).parent.resolve()
                with open(patch_path.joinpath('Super Junkoid 1.3.ips'), 'rb') as file:
                    patch_data = file.read()
                self.rom_data = patch(self.rom_data, patch_data)
                assert len(self.rom_data) == 4194304, f"patch made file {len(self.rom_data)}"
            else:
                raise ValueError(f"invalid rom {len(self.rom_data)} - need super junkoid 1.3 or vanilla SM, unheadered")
