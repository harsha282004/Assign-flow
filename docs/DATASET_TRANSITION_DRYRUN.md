# Dataset transition: dry-run report, target 15 faculty + 50 students (NOTHING APPLIED)

Corrected target: 15 faculty and 50 students (CSE-5A 17, CSE-5B 17, CSE-5C 16). An earlier version of this file used a 150-student
target by mistake (see the implementation log). Produced by `docker compose run --rm backend python -m app.db.transition_dataset --verbose`
against the real database. A dry run reads the database and changes nothing.

Before: 250 accounts (50 faculty, 200 students), 8 sections of 25 students (CSE-1A/1B/3A/3B/5A/5B/7A/7B).
After (if applied): 65 accounts (15 faculty, 50 students), 3 sections: CSE-5A 17, CSE-5B 17, CSE-5C 16.

Existing records NOT touched: 2 assignments (DBMS, os), 1 submission with 1 version, 1 late request, 2 reviews, 4 notifications
(all FAC001 / STU0102 / CS503 / CSE-5A). STU0101 and STU0102 stay in CSE-5A; FAC001 keeps CS503 / CSE-5A.

```
Target dataset: 15 faculty, 50 students
  accounts to rename      : 65
  students to move        : 24
  accounts to remove      : 185
  sections to remove      : ['CSE-1A', 'CSE-1B', 'CSE-3A', 'CSE-3B', 'CSE-7A', 'CSE-7B']
  subjects to remove      : ['CS101', 'CS102', 'CS103', 'CS104', 'CS105', 'CS106', 'CS301', 'CS302', 'CS303', 'CS304', 'CS305', 'CS306', 'CS701', 'CS702', 'CS703', 'CS704', 'CS705', 'CS706']
  teaching rows to rewrite: 47

DEPENDENT-RECORD CHECKS (row counts found; every one must be 0)
  assignments.created_by rows referencing accounts to REMOVE: 0
  notifications.user_id rows referencing accounts to REMOVE: 0
  deadline_changes.changed_by rows referencing accounts to REMOVE: 0
  late_requests.decided_by rows referencing accounts to REMOVE: 0
  late_requests.student_id rows referencing accounts to REMOVE: 0
  submissions.student_id rows referencing accounts to REMOVE: 0
  submission_versions.uploaded_by rows referencing accounts to REMOVE: 0
  reviews.reviewer_id rows referencing accounts to REMOVE: 0
  assignment_attachments.uploaded_by rows referencing accounts to REMOVE: 0
  assignments.created_by rows referencing each moving student (to MOVE): 0
  notifications.user_id rows referencing each moving student (to MOVE): 0
  deadline_changes.changed_by rows referencing each moving student (to MOVE): 0
  late_requests.decided_by rows referencing each moving student (to MOVE): 0
  late_requests.student_id rows referencing each moving student (to MOVE): 0
  submissions.student_id rows referencing each moving student (to MOVE): 0
  submission_versions.uploaded_by rows referencing each moving student (to MOVE): 0
  reviews.reviewer_id rows referencing each moving student (to MOVE): 0
  assignment_attachments.uploaded_by rows referencing each moving student (to MOVE): 0
  assignments.section_id rows referencing sections to REMOVE: 0
  assignments.subject_id rows referencing subjects to REMOVE: 0

RENAMES (login: old name -> new name)
  FAC001: Jason Thakkar -> Aarav Sharma
  FAC002: Qadim Shenoy -> Rahul Shah
  FAC003: Ethan Sur -> Kunal Pillai
  FAC004: Zarna Tella -> Prakash Prabhu
  FAC005: Shravya Choudhry -> Harish Mukherjee
  FAC006: Aadhya Sabharwal -> Neha Rao
  FAC007: Ojasvi Pandey -> Tanvi Deshpande
  FAC008: Wishi Sant -> Sowmya Bhat
  FAC009: Daksh Lanka -> Madhuri Chatterjee
  FAC010: Gautam Shetty -> Arjun Nair
  FAC011: Chakrika De -> Manish Joshi
  FAC012: Arjun Kalla -> Deepak Hegde
  FAC013: Anusha Bawa -> Naveen Mishra
  FAC014: Yamini Garde -> Diya Verma
  FAC015: Frado Butala -> Riya Gupta
  STU0101: Aadi Doshi -> Lakshmi Naidu
  STU0102: Rajata Jaggi -> Gayatri Singh
  STU0103: Avi Sidhu -> Shruti Bose
  STU0104: Chaitaly Gole -> Siddharth Patel
  STU0105: Urvashi Sabharwal -> Harsh Menon
  STU0106: Abhiram Brahmbhatt -> Anil Kamath
  STU0107: Jasmit Borra -> Venkatesh Das
  STU0108: Wahab Gokhale -> Meera Reddy
  STU0109: Vritti Ravel -> Swati Kulkarni
  STU0110: Watika Sachar -> Sahana Shetty
  STU0111: Gautami Pau -> Lavanya Banerjee
  STU0112: Jasmit Ben -> Aditya Iyer
  STU0113: Deepa Mander -> Sanjay Agarwal
  STU0114: Orinder Chada -> Ankit Gowda
  STU0115: Jason Ram -> Ganesh Chauhan
  STU0116: Anthony Saran -> Ananya Sharma
  STU0117: Nimrat Mani -> Priya Shah
  STU0118: Charita Thakkar -> Divya Pillai
  STU0119: Zaitra Parsa -> Deepika Prabhu
  STU0120: Imaran Arora -> Rashmi Mukherjee
  STU0121: Eesha Garde -> Karthik Rao
  STU0122: Teerth Oak -> Pranav Deshpande
  STU0123: Siddharth Ghosh -> Ramesh Bhat
  STU0124: Jhalak Dubey -> Srinivas Chatterjee
  STU0125: Veer Mannan -> Kavya Nair
  STU0126: Rachita Pal -> Shreya Joshi
  STU0127: Niharika Konda -> Radhika Hegde
  STU0128: Madhavi Balan -> Kritika Mishra
  STU0129: Advik Pant -> Vivaan Verma
  STU0130: Jeevika Dara -> Vikram Gupta
  STU0131: Ekapad Contractor -> Varun Naidu
  STU0132: Yug Bhatnagar -> Mahesh Singh
  STU0133: Isaac Kaur -> Raghav Bose
  STU0134: Reva Sundaram -> Pooja Patel
  STU0135: Raksha Dixit -> Aditi Menon
  STU0136: Kritika Pau -> Anjali Kamath
  STU0137: Jyoti Contractor -> Pallavi Das
  STU0138: Hemani Prabhu -> Rohan Reddy
  STU0139: Urvi Mistry -> Nikhil Kulkarni
  STU0140: Jeet Basu -> Suresh Shetty
  STU0141: Krishna Parmer -> Kiran Banerjee
  STU0142: Xalak Vala -> Isha Iyer
  STU0143: Inaya Jayaraman -> Sneha Agarwal
  STU0144: Benjamin Balan -> Nandini Gowda
  STU0145: Upma Pandit -> Jyoti Chauhan
  STU0146: Wishi Shan -> Aarav Kulkarni
  STU0147: Mekhala Dewan -> Rahul Shetty
  STU0148: Mekhala Mangal -> Kunal Banerjee
  STU0149: Vaishnavi Nair -> Prakash Iyer
  STU0150: Vihaan Batra -> Harish Agarwal

STUDENT SECTION MOVES
  STU0118: CSE-5A -> CSE-5B
  STU0119: CSE-5A -> CSE-5B
  STU0120: CSE-5A -> CSE-5B
  STU0121: CSE-5A -> CSE-5B
  STU0122: CSE-5A -> CSE-5B
  STU0123: CSE-5A -> CSE-5B
  STU0124: CSE-5A -> CSE-5B
  STU0125: CSE-5A -> CSE-5B
  STU0135: CSE-5B -> CSE-5C
  STU0136: CSE-5B -> CSE-5C
  STU0137: CSE-5B -> CSE-5C
  STU0138: CSE-5B -> CSE-5C
  STU0139: CSE-5B -> CSE-5C
  STU0140: CSE-5B -> CSE-5C
  STU0141: CSE-5B -> CSE-5C
  STU0142: CSE-5B -> CSE-5C
  STU0143: CSE-5B -> CSE-5C
  STU0144: CSE-5B -> CSE-5C
  STU0145: CSE-5B -> CSE-5C
  STU0146: CSE-5B -> CSE-5C
  STU0147: CSE-5B -> CSE-5C
  STU0148: CSE-5B -> CSE-5C
  STU0149: CSE-5B -> CSE-5C
  STU0150: CSE-5B -> CSE-5C

ACCOUNTS TO REMOVE
  FAC016, FAC017, FAC018, FAC019, FAC020, FAC021, FAC022, FAC023, FAC024, FAC025, FAC026, FAC027, FAC028, FAC029, FAC030, FAC031, FAC032, FAC033, FAC034, FAC035, FAC036, FAC037, FAC038, FAC039, FAC040, FAC041, FAC042, FAC043, FAC044, FAC045, FAC046, FAC047, FAC048, FAC049, FAC050, STU0001, STU0002, STU0003, STU0004, STU0005, STU0006, STU0007, STU0008, STU0009, STU0010, STU0011, STU0012, STU0013, STU0014, STU0015, STU0016, STU0017, STU0018, STU0019, STU0020, STU0021, STU0022, STU0023, STU0024, STU0025, STU0026, STU0027, STU0028, STU0029, STU0030, STU0031, STU0032, STU0033, STU0034, STU0035, STU0036, STU0037, STU0038, STU0039, STU0040, STU0041, STU0042, STU0043, STU0044, STU0045, STU0046, STU0047, STU0048, STU0049, STU0050, STU0051, STU0052, STU0053, STU0054, STU0055, STU0056, STU0057, STU0058, STU0059, STU0060, STU0061, STU0062, STU0063, STU0064, STU0065, STU0066, STU0067, STU0068, STU0069, STU0070, STU0071, STU0072, STU0073, STU0074, STU0075, STU0076, STU0077, STU0078, STU0079, STU0080, STU0081, STU0082, STU0083, STU0084, STU0085, STU0086, STU0087, STU0088, STU0089, STU0090, STU0091, STU0092, STU0093, STU0094, STU0095, STU0096, STU0097, STU0098, STU0099, STU0100, STU0151, STU0152, STU0153, STU0154, STU0155, STU0156, STU0157, STU0158, STU0159, STU0160, STU0161, STU0162, STU0163, STU0164, STU0165, STU0166, STU0167, STU0168, STU0169, STU0170, STU0171, STU0172, STU0173, STU0174, STU0175, STU0176, STU0177, STU0178, STU0179, STU0180, STU0181, STU0182, STU0183, STU0184, STU0185, STU0186, STU0187, STU0188, STU0189, STU0190, STU0191, STU0192, STU0193, STU0194, STU0195, STU0196, STU0197, STU0198, STU0199, STU0200

TEACHING ROWS TO REWRITE (subject, section, current teacher)
  CS101 CSE-1A FAC002
  CS101 CSE-1B FAC008
  CS102 CSE-1A FAC003
  CS102 CSE-1B FAC009
  CS103 CSE-1A FAC004
  CS103 CSE-1B FAC010
  CS104 CSE-1A FAC005
  CS104 CSE-1B FAC011
  CS105 CSE-1A FAC006
  CS105 CSE-1B FAC012
  CS106 CSE-1A FAC007
  CS106 CSE-1B FAC013
  CS301 CSE-3A FAC014
  CS301 CSE-3B FAC020
  CS302 CSE-3A FAC015
  CS302 CSE-3B FAC021
  CS303 CSE-3A FAC016
  CS303 CSE-3B FAC022
  CS304 CSE-3A FAC017
  CS304 CSE-3B FAC023
  CS305 CSE-3A FAC018
  CS305 CSE-3B FAC024
  CS306 CSE-3A FAC019
  CS306 CSE-3B FAC025
  CS501 CSE-5A FAC026
  CS501 CSE-5B FAC031
  CS502 CSE-5A FAC027
  CS502 CSE-5B FAC032
  CS503 CSE-5B FAC033
  CS504 CSE-5A FAC028
  CS504 CSE-5B FAC034
  CS505 CSE-5A FAC029
  CS505 CSE-5B FAC035
  CS506 CSE-5A FAC030
  CS506 CSE-5B FAC036
  CS701 CSE-7A FAC037
  CS701 CSE-7B FAC043
  CS702 CSE-7A FAC038
  CS702 CSE-7B FAC044
  CS703 CSE-7A FAC039
  CS703 CSE-7B FAC045
  CS704 CSE-7A FAC040
  CS704 CSE-7B FAC046
  CS705 CSE-7A FAC041
  CS705 CSE-7B FAC047
  CS706 CSE-7A FAC042
  CS706 CSE-7B FAC048
No dependent records found. Dry run: nothing changed.
```
