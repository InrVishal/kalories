import struct
import zlib
import os

def create_png(width, height, filepath):
    """Create a simple PNG with a purple circle and white K."""
    
    def pixel(x, y):
        cx, cy = width // 2, height // 2
        r = min(width, height) // 2 - 2
        dist_sq = (x - cx) ** 2 + (y - cy) ** 2
        if dist_sq <= r * r:
            # Inside circle - purple
            return (0x6C, 0x63, 0xFF, 255)
        else:
            # Outside - transparent
            return (0, 0, 0, 0)

    # Build raw pixel data with filter bytes
    raw = b""
    for y in range(height):
        raw += b"\x00"  # filter: none
        for x in range(width):
            r, g, b, a = pixel(x, y)
            raw += struct.pack("BBBB", r, g, b, a)

    # Compress
    compressed = zlib.compress(raw)

    # PNG signature
    signature = b"\x89PNG\r\n\x1a\n"

    # IHDR chunk
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    ihdr = make_chunk(b"IHDR", ihdr_data)

    # IDAT chunk
    idat = make_chunk(b"IDAT", compressed)

    # IEND chunk
    iend = make_chunk(b"IEND", b"")

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "wb") as f:
        f.write(signature + ihdr + idat + iend)
    print(f"Created {filepath} ({os.path.getsize(filepath)} bytes)")


def make_chunk(chunk_type, data):
    chunk = chunk_type + data
    return struct.pack(">I", len(data)) + chunk + struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)


base = r"c:\Users\visha\OneDrive\Desktop\kalories\app\src\main\res"

# Create icons at different densities
sizes = {
    "mipmap-mdpi": 48,
    "mipmap-hdpi": 72,
    "mipmap-xhdpi": 96,
    "mipmap-xxhdpi": 144,
    "mipmap-xxxhdpi": 192,
}

for folder, size in sizes.items():
    path = os.path.join(base, folder, "ic_launcher.png")
    create_png(size, size, path)

print("All launcher icons created!")
