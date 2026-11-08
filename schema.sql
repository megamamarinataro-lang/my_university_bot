CREATE TABLE IF NOT EXISTS specialties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS classrooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS groups (
    group_name VARCHAR(255) PRIMARY KEY,
    specialty_id INTEGER,
    course_number INTEGER,
    FOREIGN KEY (specialty_id) REFERENCES specialties (id)
);

CREATE TABLE IF NOT EXISTS users (
    username VARCHAR(255) PRIMARY KEY,
    password VARCHAR(255) NOT NULL,
    role VARCHAR(255) NOT NULL,
    group_name VARCHAR(255),
    has_accepted_fz152 BOOLEAN,
    email VARCHAR(255),
    FOREIGN KEY (group_name) REFERENCES groups (group_name)
);

CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    classroom_id INTEGER,
    teacher_username VARCHAR(255),
    date DATE,
    lesson_number INTEGER,
    FOREIGN KEY (classroom_id) REFERENCES classrooms (id),
    FOREIGN KEY (teacher_username) REFERENCES users (username)
);

CREATE TABLE IF NOT EXISTS schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_name VARCHAR(255),
    day_of_week TEXT,
    lesson_number INTEGER,
    subject VARCHAR(255),
    classroom_id INTEGER,
    teacher_username TEXT,
    FOREIGN KEY (group_name) REFERENCES groups (group_name),
    FOREIGN KEY (classroom_id) REFERENCES classrooms (id)
);

CREATE TABLE IF NOT EXISTS homeworks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_name VARCHAR(255),
    subject VARCHAR(255),
    task_text TEXT,
    deadline DATE,
    FOREIGN KEY (group_name) REFERENCES groups (group_name)
);

CREATE TABLE IF NOT EXISTS grades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_username VARCHAR(255),
    subject VARCHAR(255),
    grade_value VARCHAR(255),
    date_given DATE,
    FOREIGN KEY (student_username) REFERENCES users (username)
);

CREATE TABLE IF NOT EXISTS applicant_info (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    courses_schedule TEXT,
    required_documents TEXT,
    academy_events TEXT
);

CREATE TABLE IF NOT EXISTS academy_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(255) NOT NULL,
    phone VARCHAR(255),
    email VARCHAR(255)
);
