from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.aac_app.models.database import CommunicationBoard, User
from src.config import DATABASE_PATH

print(f"Using Database Path: {DATABASE_PATH}")
print(f"Does it exist? {DATABASE_PATH.exists()}")

engine = create_engine(f"sqlite:///{DATABASE_PATH}")
Session = sessionmaker(bind=engine)
session = Session()

# Get student1 user
student = session.query(User).filter(User.username == "student1").first()
if student:
    print(f"Student1 ID: {student.id}")
else:
    print("Student1 not found")

boards = session.query(CommunicationBoard).all()
print(f"Found {len(boards)} boards:")
public_boards = 0
student_boards = 0

for b in boards:
    is_owned = False
    if student and b.user_id == student.id:
        student_boards += 1
        is_owned = True

    if b.is_public:
        public_boards += 1

    # print(f"ID: {b.id}, Name: {b.name}, Owner: {b.user_id}, Public: {b.is_public}")

print("\nSummary:")
print(f"Total Boards: {len(boards)}")
print(f"Public Boards: {public_boards}")
print(f"Student1 Boards: {student_boards}")

session.close()
