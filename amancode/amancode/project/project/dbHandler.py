import pymysql

def insertData(data, host, user, password, database=None):
    rowId = 0

    try:
        db = pymysql.connect(host='localhost', user='root', password='Kunal@2468', database='cfis')
        cursor = db.cursor()

        query = "INSERT INTO criminaldata VALUES(0, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        values = (
            data["Name"], data["Father's Name"], data["Mother's Name"], data["Gender"],
            data["DOB(yyyy-mm-dd)"], data["Blood Group"], data["Identification Mark"],
            data["Nationality"], data["Religion"], data["Crimes Done"]
        )

        cursor.execute(query, values)
        db.commit()
        rowId = cursor.lastrowid
        print("Data stored on row %d" % rowId)
    except pymysql.Error as e:
        print("Data insertion failed:", e)
        db.rollback()
    finally:
        db.close()

    return rowId

def retrieveData(name, host, user, password, database):
    id = None
    crim_data = None

    try:
        db = pymysql.connect(host='localhost', user='root', password='Kunal@2468', database='cfis')
        cursor = db.cursor()

        query = "SELECT * FROM criminaldata WHERE name=%s"
        cursor.execute(query, (name,))
        result = cursor.fetchone()

        if result:
            id = result[0]
            crim_data = {
                "Name": result[1],
                "Father's Name": result[2],
                "Mother's Name": result[3],
                "Gender": result[4],
                "DOB(yyyy-mm-dd)": result[5],
                "Blood Group": result[6],
                "Identification Mark": result[7],
                "Nationality": result[8],
                "Religion": result[9],
                "Crimes Done": result[10]
            }
            print("Data retrieved")
        else:
            print("No data found for the provided name")
    except pymysql.Error as e:
        print("Error: Unable to fetch data:", e)
    finally:
        db.close()

    return (id, crim_data)
