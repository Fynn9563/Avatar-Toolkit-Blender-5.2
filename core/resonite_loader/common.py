import ctypes
import typing
import struct
from io import BytesIO
from typing import Any

def writeNullable(data: BytesIO, value: Any = None):
    data.write(struct.pack("?", value == None))
    if(value == None):
        return
    data.write()

def ReadCSharp_str(data: BytesIO) -> str:
    charamount = read7bitEncoded_int(data)
    string: str = data.read(charamount).decode('utf-8', errors="replace")
    #print("read string: "+string)
    return string

def WriteCSharp_str(data: BytesIO, string: str):
    encoded = string.encode('utf-8')
    write7bitEncoded_int(data, len(encoded))
    return data.write(encoded)

def read7bitEncoded_ulong(data: BytesIO) -> int:
        num: int = int(0)
        num2: int = 0
        flag: bool = True
        
        while (flag):
            b: int = int(struct.unpack('<B', data.read(1))[0])
            flag = ((b & 128) > 0)
            num |= ((b & 127) << num2)
            num2 += 7
            if not flag:
                break

        return num

def read7bitEncoded_int(data: BytesIO) -> int:
        num: int = int(0)
        num2:int = int(0)
        while (num2 != 35):
            b: int = int(struct.unpack('<B', data.read(1))[0])
            num |= int(b & 127) << num2
            num2 += 7
            if ((b & 128) == 0):
                return num
        return -1

def write7bitEncoded_ulong(data: BytesIO, integer: int) -> None:
    if not 0 <= integer < 2**64:
        raise ValueError('Unsigned 7-bit value is out of range')
    while integer >= 128:
        data.write(bytes([(integer & 127) | 128]))
        integer >>= 7
    data.write(bytes([integer]))


def write7bitEncoded_int(data: BytesIO, value: int) -> None:
    if not 0 <= value < 2**31:
        raise ValueError('Length is out of range')
    write7bitEncoded_ulong(data, value)
