#!/usr/bin/env python3
"""
Modify the LIQD app logo - change only the gray 'app' text to baby blue
Preserves everything else including background
"""
from PIL import Image
import numpy as np

def modify_logo_app_text(input_path, output_path):
    # Load the original image
    img = Image.open(input_path)
    img_rgba = img.convert('RGBA')
    data = np.array(img_rgba, dtype=np.uint8)

    height, width = data.shape[:2]
    print(f"Image size: {width}x{height}")

    # Sample the baby blue color from the "D" area (right side, upper portion)
    # Looking at pixels in the D region to get exact color
    baby_blue_samples = []
    for y in range(int(height * 0.15), int(height * 0.45)):
        for x in range(int(width * 0.75), int(width * 0.92)):
            r, g, b, a = data[y, x]
            # Find blue pixels (b > r and b > g, and not too dark)
            if a > 200 and b > r + 20 and b > g + 20 and b > 150:
                baby_blue_samples.append((r, g, b))

    if baby_blue_samples:
        avg_r = int(np.median([s[0] for s in baby_blue_samples]))
        avg_g = int(np.median([s[1] for s in baby_blue_samples]))
        avg_b = int(np.median([s[2] for s in baby_blue_samples]))
        baby_blue = (avg_r, avg_g, avg_b)
        print(f"Baby blue from 'D': RGB{baby_blue} = #{avg_r:02x}{avg_g:02x}{avg_b:02x}")
    else:
        baby_blue = (135, 206, 235)
        print(f"Using standard baby blue: RGB{baby_blue}")

    # Now find and replace gray pixels ONLY in the "app" text area (bottom half)
    modifications = 0
    for y in range(int(height * 0.52), height):
        for x in range(width):
            r, g, b, a = data[y, x]

            # Only modify visible pixels
            if a > 200:
                # Detect gray: R, G, B are similar and in gray range
                r_g_diff = abs(int(r) - int(g))
                g_b_diff = abs(int(g) - int(b))
                r_b_diff = abs(int(r) - int(b))

                # If all channels are within 20 of each other and in gray range
                if (r_g_diff < 20 and g_b_diff < 20 and r_b_diff < 20 and
                    170 < r < 210 and 170 < g < 210 and 170 < b < 210):
                    # Replace with baby blue
                    data[y, x] = [baby_blue[0], baby_blue[1], baby_blue[2], a]
                    modifications += 1

    print(f"Modified {modifications} pixels")

    # Save the result
    result_img = Image.fromarray(data, 'RGBA')
    result_img.save(output_path)
    print(f"Saved to: {output_path}")

    return output_path

if __name__ == "__main__":
    # You'll need to provide the original logo path
    input_file = "LIQDapp_branding/original_logo.png"
    output_file = "LIQDapp_branding/logo_app_baby_blue.png"

    try:
        modify_logo_app_text(input_file, output_file)
        print("\n✓ Success! Logo modified with baby blue 'app' text")
    except FileNotFoundError:
        print(f"Error: Could not find {input_file}")
        print("Please save your original logo as 'LIQDapp_branding/original_logo.png'")
