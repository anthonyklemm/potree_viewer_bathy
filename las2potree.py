# -*- coding: utf-8 -*-
"""
Created on Thu Jul 10 16:50:36 2025

@author: Anthony.R.Klemm

This script is modified to generate a Potree HTML file that uses
a local 'libs' folder to ensure library compatibility and fix errors.
"""

import geopandas as gpd
import pdal
import json
import os
import sys
import shutil
import subprocess
import webbrowser
import time

# --- 1. SET CONFIGURATION ---
POTREE_CONVERTER_EXECUTABLE = r"E:\pointcloud\potree\PotreeConverter_1.7_windows_x64\PotreeConverter.exe"

# The root directory to search recursively for .las or .laz files
ROOT_DATA_DIRECTORY = "E:/pointcloud/small"

# Path to the shapefile that defines your Area of Interest (AOI)
SHAPEFILE_AOI_FILE = r"E:\pointcloud\wreck_smallACHARE(A).shp"

# The directory where the final project will be saved.
FINAL_OUTPUT_DIRECTORY = "E:/pointcloud/potree"

# The base name for the output files.
OUTPUT_FILENAME_BASE = "shipwreck_small_23"


# --- 2. PREPARE PATHS ---

final_laz_path = os.path.join(FINAL_OUTPUT_DIRECTORY, f"{OUTPUT_FILENAME_BASE}.laz")
# Path for our new, custom HTML file
custom_html_path = os.path.join(FINAL_OUTPUT_DIRECTORY, f"{OUTPUT_FILENAME_BASE}_custom.html")


# --- 3. FIND ALL LAS/LAZ FILES ---
print(f"Searching for .las/.laz files in: {ROOT_DATA_DIRECTORY}")
las_files_to_process = []
for root, dirs, files in os.walk(ROOT_DATA_DIRECTORY):
    for file in files:
        if file.lower().endswith((".las", ".laz")):
            las_files_to_process.append(os.path.join(root, file))

if not las_files_to_process:
    print(f"Error: No .las or .laz files found in '{ROOT_DATA_DIRECTORY}'.")
    sys.exit(1)
print(f"Found {len(las_files_to_process)} files to process.")


# --- 4. READ SHAPEFILE AND GET BOUNDING BOX / CRS ---
print(f"\nReading AOI from shapefile: {SHAPEFILE_AOI_FILE}")
if not os.path.exists(SHAPEFILE_AOI_FILE):
    print(f"Error: Shapefile not found at '{SHAPEFILE_AOI_FILE}'")
    sys.exit(1)

try:
    aoi_gdf = gpd.read_file(SHAPEFILE_AOI_FILE)
except Exception as e:
    print(f"Error: Could not read shapefile. Error: {e}")
    sys.exit(1)

shapefile_crs = aoi_gdf.crs
if not shapefile_crs:
    print("Error: Shapefile does not have a Coordinate Reference System (CRS) defined.")
    sys.exit(1)

print(f"Shapefile CRS detected: {shapefile_crs.to_string()}")
bounds = aoi_gdf.total_bounds
pdal_bounds = f"([{bounds[0]}, {bounds[2]}], [{bounds[1]}, {bounds[3]}])"
print(f"Extracted Bounding Box (in shapefile's CRS): {pdal_bounds}")


# --- 5. CREATE OUTPUT DIRECTORY ---
if not os.path.exists(FINAL_OUTPUT_DIRECTORY):
    print(f"\nCreating new output directory: {FINAL_OUTPUT_DIRECTORY}")
    os.makedirs(FINAL_OUTPUT_DIRECTORY)


# --- 6. BUILD AND EXECUTE PDAL PIPELINE ---
if os.path.exists(final_laz_path):
    print(f"\nFound existing clipped file at '{final_laz_path}'. Deleting to ensure a fresh run.")
    os.remove(final_laz_path)

print("\nExecuting PDAL pipeline to clip, filter, and merge into a .LAZ file...")
pipeline_stages = [{"type": "readers.las", "filename": f} for f in las_files_to_process]
pipeline_stages.extend([
    {"type": "filters.reprojection", "out_srs": shapefile_crs.to_wkt()},
    {"type": "filters.crop", "bounds": pdal_bounds},
    # filter to remove points flagged as "Withheld" (mapped over from "rejected" from HIPS data)
    {
        "type": "filters.range",
        "limits": "Withheld[0:0]"
    },
    {
        "type": "writers.las", "filename": final_laz_path,
        "compression": "lazperf",
        "forward": "all", "offset_x": "auto", "offset_y": "auto", "offset_z": "auto",
        "scale_x": "auto", "scale_y": "auto", "scale_z": "auto"
    }
])
try:
    pipeline = pdal.Pipeline(json.dumps({"pipeline": pipeline_stages}))
    count = pipeline.execute()
    if count > 0:
        print(f"PDAL complete. Processed {count} points into: {final_laz_path}")
    else:
        print("Warning: PDAL processed 0 points. No output will be generated.")
        sys.exit(0)
except Exception as e:
    print(f"Error: PDAL pipeline failed. Error: {e}")
    sys.exit(1)


# --- 7. INSPECT THE CREATED LAZ FILE TO GET MIN/MAX elevation values ---
print("\n--- Inspecting Attributes of Clipped LAZ File ---")
min_z, max_z = 0, 0
try:
    info_command = ["pdal", "info", "--stats", final_laz_path]
    result = subprocess.run(info_command, check=True, capture_output=True, text=True, shell=True)
    metadata = json.loads(result.stdout)
    stats = metadata['stats']['statistic'][2] # Z is the 3rd dimension
    min_z, max_z = stats['minimum'], stats['maximum']
    print(f"Header Statistics for Z Dimension: Min Z: {min_z}, Max Z: {max_z}")
except Exception as e:
    print(f"Could not inspect LAZ file attributes. Error: {e}. Falling back to hardcoded values.")
    min_z, max_z = -40, -5


# --- 8. RUN POTREECONVERTER ---
print("\n--- Running PotreeConverter ---")
potree_command = [
    POTREE_CONVERTER_EXECUTABLE,
    final_laz_path, # Using .laz file as input
    "-o", FINAL_OUTPUT_DIRECTORY,
    "--generate-page", OUTPUT_FILENAME_BASE
]
print(f"Executing command: {' '.join(potree_command)}")
try:
    potree_data_dir = os.path.join(FINAL_OUTPUT_DIRECTORY, "pointclouds", OUTPUT_FILENAME_BASE)
    if os.path.exists(potree_data_dir):
        print("Potree data directory already exists. Deleting to regenerate.")
        shutil.rmtree(potree_data_dir)
        
    subprocess.run(potree_command, check=True, capture_output=True, text=True, shell=True)
    print("PotreeConverter executed successfully.")

except FileNotFoundError:
    print(f"Error: PotreeConverter not found at '{POTREE_CONVERTER_EXECUTABLE}'")
    sys.exit(1)
except subprocess.CalledProcessError as e:
    print(f"--- Error during PotreeConverter execution ---\nSTDERR: {e.stderr}")
    sys.exit(1)


# --- 9. GENERATE HTML WITH DYNAMIC VIEW ---
print(f"\nGenerating custom HTML file with a dynamic initial view: {custom_html_path}")

# Calculate center point and a good camera position from the shapefile bounds
minx, miny, maxx, maxy = bounds
center_x = (minx + maxx) / 2
center_y = (miny + maxy) / 2
center_z = (min_z + max_z) / 2

span_x = maxx - minx
span_y = maxy - miny
diagonal = (span_x**2 + span_y**2)**0.5

# Set camera position back from the center and up for a good perspective
cam_pos_x = center_x
cam_pos_y = center_y - diagonal * 1.2
cam_pos_z = center_z + diagonal * 0.5

# Set the camera to look at the center of the data
look_at_x = center_x
look_at_y = center_y
look_at_z = center_z

potree_metadata_path = f"pointclouds/{OUTPUT_FILENAME_BASE}/cloud.js"

html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
	<meta charset="utf-8">
	<meta name="description" content="">
	<meta name="author" content="">
	<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
	<title>Potree Viewer - {OUTPUT_FILENAME_BASE}</title>

	<!-- Reverting to all local libraries to ensure compatibility -->
	<link rel="stylesheet" type="text/css" href="libs/potree/potree.css">
	<link rel="stylesheet" type="text/css" href="libs/jquery-ui/jquery-ui.min.css">
	<link rel="stylesheet" type="text/css" href="libs/openlayers3/ol.css">
	<link rel="stylesheet" type="text/css" href="libs/spectrum/spectrum.css">
	<link rel="stylesheet" type="text/css" href="libs/jstree/themes/mixed/style.css">
</head>

<body>
	<!-- Reverting to all local libraries to ensure compatibility -->
	<script src="libs/jquery/jquery-3.1.1.min.js"></script>
	<script src="libs/spectrum/spectrum.js"></script>
	<script src="libs/jquery-ui/jquery-ui.min.js"></script>
	<script src="libs/three.js/build/three.min.js"></script>
	<script src="libs/other/BinaryHeap.js"></script>
	<script src="libs/tween/tween.min.js"></script>
	<script src="libs/d3/d3.js"></script>
	<script src="libs/proj4/proj4.js"></script>
	<script src="libs/openlayers3/ol.js"></script>
	<script src="libs/i18next/i18next.js"></script>
	<script src="libs/jstree/jstree.js"></script>
	<script src="libs/potree/potree.js"></script>
	<script src="libs/plasio/js/laslaz.js"></script>
	
	<div class="potree_container" style="position: absolute; width: 100%; height: 100%; left: 0px; top: 0px; ">
		<div id="potree_render_area"></div>
		<div id="potree_sidebar_container"> </div>
	</div>
	
	<script>
		// Use window.onload to ensure all local and CDN scripts are fully loaded
		// before trying to initialize the viewer.
		window.onload = function() {{
			try {{
				// Set the worker path to the local directory
				Potree.workerPath = "libs/potree/workers";

				window.viewer = new Potree.Viewer(document.getElementById("potree_render_area"));
				
				viewer.setEDLEnabled(true);
				viewer.setFOV(60);
				viewer.setPointBudget(3_000_000);
				viewer.loadSettingsFromURL();
				
				viewer.loadGUI(() => {{
					viewer.setLanguage('en');
					$("#menu_appearance").next().show();
					$("#menu_tools").next().show();
					viewer.toggleSidebar();
				}});
				
				Potree.loadPointCloud("{potree_metadata_path}", "{OUTPUT_FILENAME_BASE}", e => {{
					let pointcloud = e.pointcloud;
					viewer.scene.addPointCloud(pointcloud);
					let material = pointcloud.material;
					
					// --- OUR CUSTOM SETTINGS ---
					material.activeAttributeName = "elevation";
					material.gradient = Potree.Gradients.VIRIDIS;
					material.elevationRange = [{min_z}, {max_z}];
					material.size = 1;
					material.pointSizeType = Potree.PointSizeType.FIXED;
					material.shape = Potree.PointShape.CIRCLE;

                    // Manually set the initial camera view with hardcoded coordinates
                    viewer.scene.view.position.set({cam_pos_x}, {cam_pos_y}, {cam_pos_z});
                    viewer.scene.view.lookAt(new THREE.Vector3({look_at_x}, {look_at_y}, {look_at_z}));
				}});
			}} catch (e) {{
				console.error("Failed to initialize Potree viewer:", e);
				document.body.innerHTML = `<h1>Error loading viewer</h1><p>Please check the developer console (F12) for details.</p><pre>${{e.stack}}</pre>`;
			}}
		}};
	</script>
</body>
</html>
"""
with open(custom_html_path, 'w') as f:
    f.write(html_content)
print(f"Custom viewer file written to: {custom_html_path}")


# --- 10. START WEB SERVER AND LAUNCH ---
print("\n--- LAUNCHING PREVIEW ---")
server_process = None
try:
    os.chdir(FINAL_OUTPUT_DIRECTORY)
    try:
        import socket
        with socket.create_connection(("localhost", 8000), timeout=0.1):
                print("Web server already running.")
    except (socket.timeout, ConnectionRefusedError):
        server_process = subprocess.Popen(["python", "-m", "http.server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"Local web server started at http://localhost:8000")
        time.sleep(2)

    url_to_open = f"http://localhost:8000/{os.path.basename(custom_html_path)}"
    webbrowser.open_new_tab(url_to_open)
    print(f"Opening {url_to_open} in your web browser.")
    print("\n----------------------------------------------------------------")
    print("The web server may be running in the background.")
    print(">>> CLOSE THE PYTHON CONSOLE WINDOW TO STOP THE SERVER. <<<")
    print("----------------------------------------------------------------")
    if server_process:
        server_process.wait()

except KeyboardInterrupt:
    print("\nScript interrupted by user. Shutting down server.")
finally:
    if server_process:
        server_process.terminate()
        server_process.wait()
        print("Web server stopped.")
