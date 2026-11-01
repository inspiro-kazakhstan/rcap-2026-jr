import cv2
import numpy as np

# Open the default webcam
camera = cv2.VideoCapture(0)

if not camera.isOpened():
    raise RuntimeError("Could not open webcam")

frame_width = int(camera.get(cv2.CAP_PROP_FRAME_WIDTH))
frame_height = int(camera.get(cv2.CAP_PROP_FRAME_HEIGHT))

MARKER_LENGTH = 0.1

camera_matrix = np.array([
    [800, 0, frame_width / 2],
    [0, 800, frame_height / 2],
    [0, 0, 1]
], dtype=np.float32)

dist_coeffs = np.zeros((5, 1), dtype=np.float32)

WARP_WIDTH = 800
WARP_HEIGHT = 800

source_points = np.float32([
    [120, 80],   # top-left
    [540, 110],  # top-right
    [610, 420],  # bottom-right
    [70, 390],   # bottom-left
])

destination_points = np.float32([
    [0, 0],
    [WARP_WIDTH - 1, 0],
    [WARP_WIDTH - 1, WARP_HEIGHT - 1],
    [0, WARP_HEIGHT - 1],
])

perspective_matrix = cv2.getPerspectiveTransform(
    source_points, destination_points
)

aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_6X6_250)
parameters = cv2.aruco.DetectorParameters()
detector = cv2.aruco.ArucoDetector(aruco_dict, parameters)

robots = {
    1: "Robot 1",
    2: "Robot 2",
    3: "Robot 3",
    4: "Robot 4",
    5: "Robot 5",
    6: "Robot 6",
    7: "Robot 7",
    8: "Robot 8"
}

try:
    while True:
        ret, frame = camera.read()
        if not ret:
            print("Could not read from webcam")
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        corners, ids, rejected = detector.detectMarkers(gray)

        grid = cv2.warpPerspective(frame, perspective_matrix, (WARP_WIDTH, WARP_HEIGHT))
        grid_width = WARP_WIDTH
        grid_height = WARP_HEIGHT

        if ids is not None:
            cv2.aruco.drawDetectedMarkers(frame, corners, ids)

            for marker_id, marker_corners in zip(ids.flatten(), corners):
                marker_id = int(marker_id)

                half = MARKER_LENGTH / 2
                object_points = np.array([
                    [-half,  half, 0],
                    [ half,  half, 0],
                    [ half, -half, 0],
                    [-half, -half, 0],
                ], dtype=np.float32)

                image_points = marker_corners.reshape(4, 2)

                ok, rvec, tvec = cv2.solvePnP(
                    object_points,
                    image_points,
                    camera_matrix,
                    dist_coeffs,
                    flags=cv2.SOLVEPNP_IPPE_SQUARE,
                )

                if not ok:
                    continue

                cv2.drawFrameAxes(frame, camera_matrix, dist_coeffs, rvec, tvec, 0.05)

                # Calculate yaw
                rotation_matrix, _ = cv2.Rodrigues(rvec)
                yaw_degrees = np.degrees(
                    np.arctan2(rotation_matrix[1, 0], rotation_matrix[0, 0])
                )
                camera_yaw = -yaw_degrees

                #Finds marker center and grid cell (1–10)
                points = marker_corners.reshape(4, 2)
                center_x = float(points[:, 0].mean())
                center_y = float(points[:, 1].mean())

                robot_name = robots.get(marker_id, "Unknown robot")

                center = np.array([[[center_x, center_y]]], dtype=np.float32)
                warped_x, warped_y = cv2.perspectiveTransform(
                    center, perspective_matrix)[0, 0]

                column = min(int(warped_x * 12 / WARP_WIDTH) + 1, 12)
                row = min(int(warped_y * 12 / WARP_HEIGHT) + 1, 12)

                print(robot_name, "позиция:", column, row, "угол:", camera_yaw)

        #Draws 12×12 grid
        for i in range(1, 12):
            x = grid_width * i // 12
            y = grid_height * i // 12
            cv2.line(grid, (x, 0), (x, grid_height), (0, 0, 255), 1)
            cv2.line(grid, (0, y), (grid_width, y), (0, 0, 255), 1)

        cv2.imshow("Webcam", frame)
        cv2.imshow("Grid", grid)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
        
finally:
    camera.release()
    cv2.destroyAllWindows()