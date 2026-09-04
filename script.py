#!.venv/bin/python3

from bs4 import BeautifulSoup
import requests
import sys
from enum import Enum
import os

class ScoreType(Enum):
    LOW = 4
    MID = 2
    HIGH = 1

def print_help():
    B = "\033[1m"      # Bold
    G = "\033[32m"     # Green
    Y = "\033[33m"     # Yellow
    C = "\033[36m"     # Cyan
    R = "\033[31m"     # Red
    D = "\033[2m"      # Dim
    RESET = "\033[0m"

    help_text = f"""
Автоматическая оценка преподавателей в системе МИФИ

{B}ИСПОЛЬЗОВАНИЕ:{RESET}
    python3 script.py [ОПЦИИ] [ПРЕПОДАВАТЕЛИ]

{B}ОПЦИИ:{RESET}
    {C}-h, --help{RESET}            Показать эту справку и выйти
    
    {C}-p, --print{RESET}           Вывести список преподавателей, не оценивая их

    {C}-s, --score=ОЦЕНКА{RESET}    Установить оценку для указанных преподавателей
                          Доступные значения: {R}low{RESET}, {Y}mid{RESET}, {G}high{RESET}
                          По умолчанию: {Y}mid{RESET}

{B}АРГУМЕНТЫ:{RESET}
    ПРЕПОДАВАТЕЛИ         Список преподавателей в формате {B}фамилия_инициалы{RESET}
                          через запятую без пробелов
                          
                          Или используйте '{B}all{RESET}' для оценки всех преподавателей

{B}ТРЕБОВАНИЯ:{RESET}
    Для работы программы необходимо установить переменные окружения:
    • {B}MEPHI_USERNAME{RESET}  — ваш логин в системе МИФИ
    • {B}MEPHI_PASSWORD{RESET}  — ваш пароль в системе МИФИ

{B}ФОРМАТ ВВОДА ПРЕПОДАВАТЕЛЕЙ:{RESET}
    {G}✓{RESET} Правильно:   сучков_мв
    {G}✓{RESET} Правильно:   петров-сидоров_аб (двойная фамилия)
    {G}✓{RESET} Правильно:   СУЧКОВ_МВ (регистр не важен)
    {G}✓{RESET} Правильно:   сучков_мв,волков_ве (несколько преподавателей)
    {R}✗{RESET} Неправильно: сучков мв (пробел вместо подчеркивания)
    {R}✗{RESET} Неправильно: сучков_мв, волков_ве (пробел после запятой)

{B}ПРИМЕРЫ:{RESET}
    {D}# Оценить конкретных преподавателей (оценка по умолчанию mid){RESET}
    python3 script.py сучков_мв,волков_ве
    
    {D}# Оценить с конкретной оценкой{RESET}
    python3 script.py -s=high сучков_мв,волков_ве
    
    {D}# Оценить всех преподавателей{RESET}
    python3 script.py all
    
    {D}# Оценить всех с низкой оценкой{RESET}
    python3 script.py -s=low all
"""
    print(help_text)


def get_input():
    if "--help" in sys.argv or "-h" in sys.argv:
        print_help()
        sys.exit(0)

    if "--print" in sys.argv or "-p" in sys.argv:
        return None, None, None, True

    score: ScoreType = ScoreType.MID
    tutor_names = []
    is_all = False

    for arg in sys.argv[1:]:
        if not arg.startswith("-"):
            names = arg.split(",")
            if "" in names:
                print("Фио преподавателей должны быть разделены запятыми без пробелов")
                print_help()
                sys.exit(1)

            if len(names) == 1 and names[0].lower() == "all":
                is_all = True
                continue
            
            tutor_names += [name.upper() for name in names]

        elif arg.startswith("--score=") or arg.startswith("-s="):
            score_s = arg.split("=")[1].upper()
            if score_s == "LOW":
                score = ScoreType.LOW
            elif score_s == "MID":
                score = ScoreType.MID
            elif score_s == "HIGH":
                score = ScoreType.HIGH
            else:
                print("Оценка может быть только одной из следующих трех: LOW/AVG/MID [регистр не имеет значения]")
                print_help()
                sys.exit(1)
        else:
            print("Такой опции не существует")
            print_help()
            sys.exit(1)

    if not is_all and not tutor_names:
        print("Вы должны ввести либо ФИО преподавателей, либо all")
        print_help()
        sys.exit(1)

    return score, tutor_names, is_all, False

def get_auth_token_and_lt(session: requests.Session, url: str, only_auth=False):
    response = session.get(url=url)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, 'html.parser')
    auth_token: str = soup.find("input", {"name": "authenticity_token"}).get("value")
    lt: str | None = None

    if not only_auth:
        lt = soup.find("input", {"name": "lt"}).get("value")
    
    return auth_token, lt


def login_into_system(session: requests.Session, username: str, password: str) -> None:
    auth_url: str = "https://auth.mephi.ru/login/"
    auth_token, lt = get_auth_token_and_lt(session, auth_url)
    
    response = session.post(
        url=auth_url,
        data={
            "authenticity_token": auth_token,
            "lt": lt,
            "username": username,
            "password": password,
        }
    )
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as err:
        print(f"Произошла ошибка при попытке входа")
        print(err)
        sys.exit(1)
    
    print("Авторизация прошла успешно")


def get_term_id_and_name(session: requests.Session):
    response = session.get("https://survey.mephi.ru/surveys/load_terms.json")

    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as err:
        print("Произошла ошибка при получении ID текущего семестра")
        print(err)
        sys.exit(1)
    
    terms = response.json()
    id: int = terms[0].get("id")
    name: str = terms[0].get("name")

    return id, name


def get_student_id_and_name(session: requests.Session, term_id: int):
    response = session.get(f"https://survey.mephi.ru/surveys/load_students.json?term_id={term_id}")

    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as err:
        print("Произошла ошибка при получении ID студента [Вашего ID]")
        print(err)
        sys.exit(1)
    
    terms = response.json()
    id: int = terms[0].get("id")
    name: str = terms[0].get("name")

    return id, name


def get_tutors(session: requests.Session, student_id: int):
    survey_url: str = "https://survey.mephi.ru/surveys/"
    courses = session.get(f"{survey_url}load_courses.json?student_id={student_id}").json()
    tutors = []

    for course in courses:
        course_tutors = session.get(f"{survey_url}load_tutors.json?course_id={course.get("id")}").json()
        
        for course_tutor in course_tutors:
            tutor_name_split = course_tutor.get("name").split()
            name = f"{tutor_name_split[0].upper()}_{tutor_name_split[1][0].upper()}" # СУЧКОВ_МВ
            try:
                otchestvo = tutor_name_split[2][0].upper()
                name += otchestvo
            except IndexError:
                pass
                
            course_tutor["name"] = name
            course_tutor["course_id"] = course.get("id")
            tutors.append(course_tutor)
    
    return tutors


def get_tutor_by_name(tutors, tutor_name: str):
    tutor = next((t for t in tutors if t["name"] == tutor_name), None)

    return tutor


def get_survey_answers_by_score(score: ScoreType):
    answers = [{
        "question_id": 1,
        "variant_id": score.value,
    }]
    
    for q_number in range(2, 18):
        answer = dict()
        answer["question_id"] = q_number

        if score == ScoreType.HIGH:
            answer["variant_id"] = (q_number-1)*6
        else:
            answer["variant_id"] = q_number*6 - (6 - score.value)
        answers.append(answer) 
    
    return answers


def post_survey(session: requests.Session, term_id: int, student_id: int, tutor, score: ScoreType):
    survey_url: str = "https://survey.mephi.ru/surveys/"
    auth_token, lt = get_auth_token_and_lt(
        session=session,
        url=f"{survey_url}new?poll_id=1",
        only_auth=True,
    )
    
    answers = get_survey_answers_by_score(score=score)

    payload = {
        "authenticity_token": auth_token,
        "poll_id": 1,
        "survey[term_id]": term_id,
        "survey[student_id]": student_id,
        "survey[course_id]": tutor.get("course_id"),
        "survey[tutor_id]": tutor.get("id"),
    }
    
    for idx, answer in enumerate(answers):
        for key, value in answer.items():
            payload[f"survey[answers_attributes][{idx}][{key}]"] = value
    
    payload[f"survey[answers_attributes][17][question_id]"] = 18 
    payload[f"survey[answers_attributes][17][body]"] = "" 
    
    post_response = session.post(url=survey_url, data=payload)
    try: 
        post_response.raise_for_status()
    except requests.exceptions.HTTPError as err:
        print(f"Произошла ошибка во время отправки отзыва: {err}")
        sys.exit(1)


def score_tutors_by_name(session: requests.Session, term_id: int, student_id: int, tutors, tutor_names, score: ScoreType):
    for name in tutor_names:
        tutor = get_tutor_by_name(tutors=tutors, tutor_name=name)

        if not tutor:
            print(f"Преподаватель {name} не найден")
            continue

        if tutor.get("disabled"):
            print(f"Преподаватель {name} уже был оценен")
            continue

        post_survey(
            session=session,
            term_id=term_id,
            student_id=student_id,
            tutor=tutor,
            score=score
        )

        print(f"Отзыв на {name} отправлен успешно")


def score_all_tutors(session: requests.Session, term_id: int, student_id: int, tutors, score: ScoreType):
    for tutor in tutors:
        name = tutor.get("name")

        if not tutor:
            print(f"Преподаватель {name} не найден")
            continue

        if tutor.get("disabled"):
            print(f"Преподаватель {name} уже был оценен")
            continue

        post_survey(
            session=session,
            term_id=term_id,
            student_id=student_id,
            tutor=tutor,
            score=score
        )

        print(f"Отзыв на {name} отправлен успешно")


def print_tutors(tutors):
    for tutor in tutors:
        status: str = "Оценен" if tutor.get("disabled") else "Не оценен"
        print(f"Преподаватель: {tutor.get("name")}; Статус: {status}")


def main() -> None:
    score, tutor_names, is_all, is_print = get_input()
    username: str | None = os.environ.get("MEPHI_USERNAME")
    password: str | None = os.environ.get("MEPHI_PASSWORD")

    if not username or not password:
        print("Переменные окружения MEPHI_USERNAME и/или MEPHI_PASSWORD не установлены")
        sys.exit(1)

    session: requests.Session = requests.Session()

    login_into_system(session=session, username=username, password=password)
    
    term_id, term_name = get_term_id_and_name(session=session)
    print(f"Сейчас идет - {term_name}")

    student_id, student_name = get_student_id_and_name(session=session, term_id=term_id)
    print(f"Вы из группы - {student_name}")

    tutors = get_tutors(session=session, student_id=student_id)
    print("Список преподавателей загружен")

    if is_print:
        print_tutors(tutors)
        sys.exit(0)

    if is_all:
        score_all_tutors(
            session=session,
            term_id=term_id,
            student_id=student_id,
            tutors=tutors,
            score=score
        )
        sys.exit(0)
    
    score_tutors_by_name(
        session=session,
        term_id=term_id,
        student_id=student_id,
        tutor_names=tutor_names,
        tutors=tutors,
        score=score
    )

if __name__ == "__main__":
    main()
