import cv2
import numpy as np
import playsound3 as sound
import time

#Opens the webcam
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
        positions = {}

        grid = frame.copy()

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
                cv2.drawFrameAxes(grid, camera_matrix, dist_coeffs, rvec, tvec, 0.05)

                #Calculates yaw
                rotation_matrix, _ = cv2.Rodrigues(rvec)
                yaw_degrees = np.degrees(
                    np.arctan2(rotation_matrix[1, 0], rotation_matrix[0, 0])
                )
                camera_yaw = yaw_degrees

                #Finds marker center and grid cell (1–10)
                points = marker_corners.reshape(4, 2)
                center_x = float(points[:, 0].mean())
                center_y = float(points[:, 1].mean())
                column = int(min(center_x * 10 // frame_width + 1, 10))
                row = int(min(center_y * 10 // frame_height + 1, 10))

                robot_name = robots.get(marker_id, "Unknown robot")

                #Pyramid
                if (positions.get(1) == (2, 9) and
                positions.get(2) == (3, 7) and
                positions.get(3) == (4, 5) and
                positions.get(4) == (5, 3) and 
                positions.get(5) == (8, 3) and 
                positions.get(6) == (9, 5) and 
                positions.get(7) == (10, 7) and 
                positions.get(8) == (11, 9)):
                    sound.playsound("wow.mp3")

                #Heart
                if (positions.get(1) == (7, 12) and 
                positions.get(2) == (4, 9) and
                positions.get(3) == (1, 4) and
                positions.get(4) == (4, 1) and
                positions.get(5) == (10, 1) and
                positions.get(6) == (12, 4) and
                positions.get(7) == (10, 9) and
                positions.get(8) == (7, 3)):
                    sound.playsound("wow.mp3")
                
                #Sun
                if (positions.get(1) == (4, 12) and 
                positions.get(2) == (1, 9) and
                positions.get(3) == (1, 4) and
                positions.get(4) == (4, 1) and
                positions.get(5) == (9, 1) and
                positions.get(6) == (12, 4) and
                positions.get(7) == (12, 9) and
                positions.get(8) == (9, 12)):
                    sound.playsound("wow.mp3")

                #Butterfly
                if (positions.get(1) == (6, 11) and 
                positions.get(2) == (3, 9) and
                positions.get(3) == (3, 5) and
                positions.get(4) == (1, 3) and
                positions.get(5) == (12, 3) and
                positions.get(6) == (10, 5) and
                positions.get(7) == (10, 9) and
                positions.get(8) == (6, 6)):
                    sound.playsound("wow.mp3")

                #Bird
                if (positions.get(1) == (6, 12) and 
                positions.get(2) == (4, 8) and
                positions.get(3) == (2, 6) and
                positions.get(4) == (1, 4) and
                positions.get(5) == (12, 4) and
                positions.get(6) == (10, 6) and
                positions.get(7) == (8, 8) and
                positions.get(8) == (6, 9)):
                    sound.playsound("wow.mp3")

                #Diamond
                if (positions.get(1) == (6, 12) and 
                positions.get(2) == (3, 9) and
                positions.get(3) == (1, 6) and
                positions.get(4) == (3, 3) and
                positions.get(5) == (6, 1) and
                positions.get(6) == (9, 3) and
                positions.get(7) == (11, 6) and
                positions.get(8) == (9, 9)):
                    sound.playsound("wow.mp3")

                print(robot_name, "позиция:", column, row, "угол:", camera_yaw)
                time.sleep(0.2)
                

        #Draws 12×12 grid
        for i in range(1, 10):
            x = frame_width * i // 10
            y = frame_height * i // 10
            cv2.line(grid, (x, 0), (x, frame_height), (0, 0, 255), 1)
            cv2.line(grid, (0, y), (frame_width, y), (0, 0, 255), 1)

        cv2.imshow("Webcam", frame)
        cv2.imshow("Grid", grid)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
        
finally:
    camera.release()
    cv2.destroyAllWindows()