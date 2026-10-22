"""カメラの映像の向きの補正。カメラが上下逆・横向きに付いている時に、画像を回してから顔を検出する（設定 camera_rotate）。"""
import cv2

_ROTATE = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}
ROTATIONS = (0, 90, 180, 270)


def rotate_image(img, deg: int):
    return cv2.rotate(img, _ROTATE[deg]) if deg in _ROTATE else img
