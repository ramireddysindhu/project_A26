import sqlite3
import ijson
import os

def import_data_from_json(json_filepath):
    """Reads a large JSON file in a stream and imports the data into an SQLite database."""
    if not os.path.exists(json_filepath):
        print(f"Error: The file '{json_filepath}' was not found.")
        return

    conn = sqlite3.connect('medicines.db')
    cursor = conn.cursor()

    # Drop existing table and create a new, clean one
    cursor.execute("DROP TABLE IF EXISTS medicines")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS medicines (
            name TEXT PRIMARY KEY,
            description TEXT,
            uses TEXT,
            side_effects TEXT
        )
    """)

    # Use ijson to parse the large file in a stream
    try:
        with open(json_filepath, 'rb') as f:
            # 'results.item' tells ijson to iterate over each item in the 'results' array
            for item in ijson.items(f, 'results.item'):
                
                # Extract drug name
                name = ""
                openfda = item.get("openfda", {})
                if "generic_name" in openfda and openfda["generic_name"]:
                    name = openfda["generic_name"][0].lower()
                elif "brand_name" in openfda and openfda["brand_name"]:
                    name = openfda["brand_name"][0].lower()
                
                # Extract uses by checking multiple possible keys
                uses = "Not available."
                if "indications_and_usage" in item and item["indications_and_usage"]:
                    uses = " ".join(item["indications_and_usage"])
                elif "pharmacology_and_toxicology" in item and item["pharmacology_and_toxicology"]:
                    uses = " ".join(item["pharmacology_and_toxicology"])

                # Extract side effects by checking multiple possible keys
                side_effects = "Not available."
                if "adverse_reactions" in item and item["adverse_reactions"]:
                    side_effects = " ".join(item["adverse_reactions"])
                elif "warnings" in item and item["warnings"]:
                    side_effects = " ".join(item["warnings"])
                elif "precautions" in item and item["precautions"]:
                    side_effects = " ".join(item["precautions"])

                description = uses # Use 'uses' as the description since they are often the same in this dataset
                
                if name:
                    cursor.execute("""
                        INSERT OR IGNORE INTO medicines (name, description, uses, side_effects)
                        VALUES (?, ?, ?, ?)
                    """, (name, description, uses, side_effects))
    
        conn.commit()
        print("Database populated successfully from JSON.")

    except ijson.common.JSONError as e:
        print(f"Error parsing JSON file: {e}. The file may be malformed.")
        conn.rollback()
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        conn.rollback()
    finally:
        conn.close()

# IMPORTANT: Make sure the JSON file is in the same folder as this script.
import_data_from_json('drug-drugsfda-0001-of-0001.json')