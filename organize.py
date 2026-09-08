import os
import shutil

# 정리할 폴더 경로 (바탕화면의 test-folder)
folder_path = r"C:\Users\user\Desktop\test-folder"

# 확장자별로 어느 폴더로 보낼지 정해두기
folder_map = {
    ".jpg": "이미지",
    ".png": "이미지",
    ".pdf": "문서",
    ".txt": "문서",
    ".docx": "문서",
    ".zip": "압축파일"
}

# 폴더 안의 파일들을 하나씩 확인
files = os.listdir(folder_path)

for filename in files:
    file_path = os.path.join(folder_path, filename)

    # 폴더는 건너뛰기 (파일만 처리)
    if os.path.isdir(file_path):
        continue

    # 확장자 추출 (예: "사진1.jpg" -> ".jpg")
    name, extension = os.path.splitext(filename)
    extension = extension.lower()

    # 이 확장자가 우리가 아는 것인지 확인
    if extension in folder_map:
        target_folder_name = folder_map[extension]
        target_folder_path = os.path.join(folder_path, target_folder_name)

        # 목적지 폴더가 없으면 새로 만들기
        if not os.path.exists(target_folder_path):
            os.makedirs(target_folder_path)

        # 파일 옮기기
        shutil.move(file_path, os.path.join(target_folder_path, filename))
        print(filename, "->", target_folder_name, "폴더로 이동")
    else:
        print(filename, "-> 알 수 없는 확장자, 건너뜀")

print("\n정리 완료!")