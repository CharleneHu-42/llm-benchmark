import csv
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('-d', '--dtype', type=str, default='int4',
                    help='Result dtype')
args = parser.parse_args()

csv_path = args.dtype + '-results.csv'

# Open the CSV file for reading
with open(csv_path, 'r') as csv_file:
    # Create a CSV reader
    csv_reader = csv.reader(csv_file)
    
    # Initialize variables to store data
    first_row_data = ""
    second_row_data = ""
    third_row_data = ""
    
    # Initialize a flag to keep track of even and odd rows
    i = 0
    
    # Iterate through the CSV rows
    for row in csv_reader:
        # Check if it's an even row
        if i%3 == 0:
            first_row_data = ', '.join(row[2:4])
        elif i%3 == 1:
            second_row_data = ', '.join(row[2:4])
        else:
            third_row_data = ', '.join(row[2:4])
            # Merge data from even and odd rows
            merged_data = first_row_data + ', ' + second_row_data + ', ' + third_row_data
            print(merged_data)
        
        # Toggle the flag for the next row
        i += 1
