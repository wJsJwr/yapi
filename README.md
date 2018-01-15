# YAPI
YAPI - Yet Another Protobuf Inspector

如果你对制作这个程序的动机感兴趣，且听我[讲个故事](http://blog.gou.cool/2018/01/a-journey-to-failure/)

`YAPI` is a simple Python script to inspect raw [Google Protobuf][] blobs without knowing their accompanying definition.

`YAPI` can parse these data types currently:

 - Varint: int32, int64, uint32, uint64, sint32, sint64, bool, enum, with or without [zig-zag encoding][]
 - 64-bit: fixed64, sfixed64, double
 - Length-delimited: string, bytes, embedded messages, packed repeated fields
 - Start group: groups (deprecated)
 - End group: groups (deprecated)
 - 32-bit: fixed32, sfixed32, float

Also, it will keep the `field_number` according to the [wire format][].

Note that when dealing with the `Length-delimited` data, it will firstly be parsed as a string. If fails or the length of the string is too long(see the Section `Parser parameters` ), the data will be parsed as `packed repeated fields`. If the number of repeated fields is too much, the data will be parsed as `embedded messages`. If all these parsing processes are failed, the data will be treated as a byte blob.

## Parser parameters

Here are some parameters you may want to adjust accroding to your project.

 - `ALLOW_STRING_LENGTH` = 100
 
    If the string parsed from `Length-delimited` data is longer than this parameter, it will be parsed as `packed repeated fields`.
    
 - `ALLOW_REPEATED_NUMBER_COUNT` = 10
 
    If the number of fields in the `packed repeated fields` is larger than this parameter, the data will be parsed as `embedded messages`.
    
 - `GUESS_TIMESTAMP` = True
 
    When the `varint` value is between 1514736000 and 1600000000, `YAPI` will treat it as a timestamp.

Feel free to dig into the code, and tune it for your own project.

## Dependency

`Python 3`. Written and tested in Python `3.6.4` and `3.6.2`

## Usage

```bash
python yapi.py file offset length
```

 - `file`: the file you want to parse

 - `offset`: start from this position

 - `length`: the length of Protobuf blob. Use `-1` to read till the end of the file.

**Note: The string is decoded in `UTF-8`. If you are using Windows, remember to call `CHCP 65001` to avoid mojibake.**

## Screenshot

![MainScreenshot](http://s.gou.cool/share/yapi.png)

[Google Protobuf]: https://developers.google.com/protocol-buffers
[Wire format]: https://developers.google.com/protocol-buffers/docs/encoding
[Zig-zag encoding]: https://developers.google.com/protocol-buffers/docs/encoding#signed-integers
