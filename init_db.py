"""Initialize the local SQLite database."""

from database import DEFAULT_DB_PATH, init_database


def main() -> None:
    init_database(DEFAULT_DB_PATH)
    print(f"数据库初始化完成：{DEFAULT_DB_PATH.resolve()}")


if __name__ == "__main__":
    main()

