import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
from datetime import datetime, timedelta
import os
import traceback

# Set page title and layout
st.set_page_config(page_title="Student Attendance Tracker & Predictor", layout="wide")

# Constants
MIN_ATTENDANCE_THRESHOLD = 75
ATTENDANCE_WARNING_THRESHOLD = 80
MAX_ATTENDANCE_PERCENTAGE = 100
MIN_ATTENDANCE_PERCENTAGE = 0

# Function to validate Excel file
def validate_excel_file(df):
    """Validate the uploaded Excel file has the expected structure."""
    # Check if file is empty
    if df.empty:
        return False, "The uploaded file is empty. Please upload a valid file."
    
    # Check if the file has at least 3 columns (Name, PRN, and at least one subject)
    if len(df.columns) < 3:
        return False, "The file must have at least 3 columns: Name, PRN, and at least one attendance column."
    
    # Check for required columns (Name and PRN)
    required_cols = ['Name', 'PRN']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        return False, f"Missing required columns: {', '.join(missing_cols)}. First two columns should be Name and PRN."
    
    # Check if there are any numeric columns (for attendance)
    numeric_cols = df.select_dtypes(include=['float64', 'int64']).columns
    if len(numeric_cols) == 0:
        return False, "No attendance columns found. Please ensure your Excel file has numerical attendance values."
    
    # Check for valid attendance values (0-100%)
    for col in numeric_cols:
        # Skip first two columns that might be ID or other values
        if col in ['Name', 'PRN']:
            continue
            
        # Check for negative values
        if (df[col] < MIN_ATTENDANCE_PERCENTAGE).any():
            return False, f"Column '{col}' contains negative attendance values, which is invalid."
        
        # Check for values over 100%
        if (df[col] > MAX_ATTENDANCE_PERCENTAGE).any():
            return False, f"Column '{col}' contains attendance values over 100%, which is invalid."
            
    return True, ""

# Function to parse Excel file
def parse_excel(uploaded_file):
    """Parse the uploaded Excel file with error handling."""
    try:
        df = pd.read_excel(uploaded_file)
        
        # Basic validation of data format
        valid, error_message = validate_excel_file(df)
        if not valid:
            return None, error_message
            
        return df, ""
    except Exception as e:
        error_msg = f"Error reading Excel file: {str(e)}"
        if "XLRDError" in str(e):
            error_msg = "File format not supported. Please save your file as a .xlsx file."
        return None, error_msg

# Function to calculate attendance
def calculate_attendance(df):
    """Calculate attendance statistics with robust error handling."""
    try:
        # Get all numeric columns except for the first two (which are name and PRN)
        all_numeric_cols = df.select_dtypes(include=['float64', 'int64']).columns
        
        # Filter out any first two columns that might be numeric
        name_prn_cols = df.columns[:2].tolist()
        attendance_cols = [col for col in all_numeric_cols if col not in name_prn_cols]
        
        # Check if we have any attendance columns
        if len(attendance_cols) == 0:
            return None, [], "No attendance columns found. Please ensure your Excel file has numerical attendance values."
        
        # Clean attendance data: clip values to valid range (0-100)
        for col in attendance_cols:
            df[col] = np.clip(df[col], MIN_ATTENDANCE_PERCENTAGE, MAX_ATTENDANCE_PERCENTAGE)
            
        # Handle NaN values by replacing with column mean
        for col in attendance_cols:
            if df[col].isna().any():
                col_mean = df[col].mean()
                df[col] = df[col].fillna(col_mean)
                st.warning(f"Missing values found in '{col}' column. Replaced with column average.")
        
        # Calculate overall attendance percentage
        df['Overall_Attendance'] = df[attendance_cols].mean(axis=1)
        
        # Mark defaulters (students with < threshold attendance)
        df['Defaulter'] = df['Overall_Attendance'] < MIN_ATTENDANCE_THRESHOLD
        
        return df, list(attendance_cols), ""
    except Exception as e:
        return None, [], f"Error calculating attendance: {str(e)}"

# Function to predict required lectures with proper error handling
def predict_required_lectures(current_attendance, total_lectures_so_far, target_percentage=MIN_ATTENDANCE_THRESHOLD):
    """Calculate the number of future lectures needed to reach target percentage."""
    try:
        # Validate inputs
        if not isinstance(current_attendance, (int, float)) or not isinstance(total_lectures_so_far, (int, float)):
            return None, "Attendance and total lectures must be numeric values."
            
        if current_attendance < MIN_ATTENDANCE_PERCENTAGE or current_attendance > MAX_ATTENDANCE_PERCENTAGE:
            return None, f"Current attendance must be between {MIN_ATTENDANCE_PERCENTAGE}% and {MAX_ATTENDANCE_PERCENTAGE}%."
            
        if total_lectures_so_far <= 0:
            return None, "Total lectures must be greater than zero."
            
        if target_percentage <= 0 or target_percentage > MAX_ATTENDANCE_PERCENTAGE:
            return None, f"Target percentage must be between 0% and {MAX_ATTENDANCE_PERCENTAGE}%."
        
        # If already above target, no need for additional lectures
        if current_attendance >= target_percentage:
            return 0, ""
        
        # Calculate how many classes attended so far
        attended_lectures = (current_attendance / 100) * total_lectures_so_far
        
        # This formula calculates additional lectures needed to reach target percentage
        # (attended_lectures + x) / (total_lectures_so_far + x) = target_percentage / 100
        
        # Handle edge case: If target is 100%, student needs to attend infinite lectures
        if target_percentage == 100:
            return float('inf'), "To reach 100% attendance, you need to attend all future lectures."
            
        # Special handling for edge case: If target is above current attendance but close to 100%
        denominator = (100 - target_percentage)
        if denominator == 0:  # Should not happen due to previous check, but just to be safe
            return float('inf'), "Target percentage is too high, formula gives undefined result."
            
        x = (target_percentage * total_lectures_so_far - 100 * attended_lectures) / denominator
        result = max(0, int(np.ceil(x)))  # Ceiling the value to ensure minimum required lectures
        
        return result, ""
    except Exception as e:
        return None, f"Error in prediction calculation: {str(e)}"

# Function to generate suggestions with error handling
def generate_suggestions(attendance_data, attendance_cols):
    """Generate personalized suggestions based on attendance data."""
    suggestions = []
    
    try:
        # Validate inputs
        if 'Overall_Attendance' not in attendance_data:
            return ["Could not generate suggestions: Missing overall attendance data."]
            
        # Check if attendance_cols exist in the data
        missing_cols = [col for col in attendance_cols if col not in attendance_data]
        if missing_cols:
            return [f"Could not generate complete suggestions: Missing data for {', '.join(missing_cols)}"]
        
        # Overall attendance suggestion
        overall_att = attendance_data['Overall_Attendance']
        if overall_att < MIN_ATTENDANCE_THRESHOLD:
            suggestions.append(f"❗ Your overall attendance is below the required {MIN_ATTENDANCE_THRESHOLD}% threshold.")
        elif overall_att < ATTENDANCE_WARNING_THRESHOLD:
            suggestions.append(f"⚠️ Your overall attendance ({overall_att:.2f}%) is just above the minimum requirement.")
        else:
            suggestions.append(f"✅ Good job! Your overall attendance ({overall_att:.2f}%) is well above the minimum requirement.")
        
        # Find subjects with low attendance
        low_attendance_subjects = []
        for col in attendance_cols:
            # Check if column exists and contains valid data
            if col in attendance_data and not pd.isna(attendance_data[col]):
                if attendance_data[col] < MIN_ATTENDANCE_THRESHOLD:
                    low_attendance_subjects.append((col, attendance_data[col]))
        
        if low_attendance_subjects:
            suggestions.append(f"⚠️ Pay attention to these subjects with low attendance:")
            for subject, att in low_attendance_subjects:
                suggestions.append(f"   - {subject}: {att:.2f}%")
        
        return suggestions
    except Exception as e:
        return [f"Error generating suggestions: {str(e)}"]

# Function to calculate projected attendance with proper error handling
def calculate_projected_attendance(current_att, total_lectures, num_future_classes, attendance_scenario, attendance_rate=0.5):
    """Calculate projected attendance based on future attendance patterns."""
    try:
        # Validate inputs
        if not all(isinstance(x, (int, float)) for x in [current_att, total_lectures, num_future_classes]):
            return None, None, "All inputs must be numeric values."
            
        if current_att < MIN_ATTENDANCE_PERCENTAGE or current_att > MAX_ATTENDANCE_PERCENTAGE:
            return None, None, f"Current attendance must be between {MIN_ATTENDANCE_PERCENTAGE}% and {MAX_ATTENDANCE_PERCENTAGE}%."
            
        if total_lectures <= 0 or num_future_classes < 0:
            return None, None, "Lecture counts must be positive values."
            
        if attendance_rate < 0 or attendance_rate > 1:
            return None, None, "Attendance rate must be between 0 and 1."
        
        # Calculate current attended lectures
        current_attended = (current_att / 100) * total_lectures
        
        # Determine future attended lectures based on scenario
        if attendance_scenario == "Attend all classes":
            future_attended = num_future_classes
        elif attendance_scenario == "Miss all classes":
            future_attended = 0
        else:  # Attend some classes
            future_attended = int(num_future_classes * attendance_rate)
        
        # Calculate new attendance statistics
        new_total_lectures = total_lectures + num_future_classes
        new_attended = current_attended + future_attended
        new_percentage = (new_attended / new_total_lectures) * 100 if new_total_lectures > 0 else 0
        
        # Generate dates and projected attendance over time
        today = datetime.now()
        future_dates = [today + timedelta(days=i*7//max(1, num_future_classes)) for i in range(num_future_classes+1)]
        
        projected_attendance = []
        running_total = total_lectures
        running_attended = current_attended
        
        for i in range(num_future_classes+1):
            if i == 0:
                # Initial attendance
                projected_attendance.append(current_att)
            else:
                # Determine attendance for this class
                if attendance_scenario == "Attend all classes":
                    attend = 1
                elif attendance_scenario == "Miss all classes":
                    attend = 0
                else:  # Attend some classes
                    # More realistic - distribute attendance evenly
                    attend = 1 if i <= future_attended else 0
                
                # Update running totals
                running_attended += attend
                running_total += 1
                
                # Calculate new percentage directly from running totals to avoid compounding errors
                new_att = (running_attended / running_total) * 100
                projected_attendance.append(new_att)
        
        return new_percentage, list(zip(future_dates, projected_attendance)), ""
    except Exception as e:
        return None, None, f"Error calculating projected attendance: {str(e)}"

# Main app title with version
st.title("Student Attendance Tracker & Predictor System")
st.write("Maintaining the required attendance percentage is crucial for students to avail academic benefits and eligibility criteria in colleges.")

# Sidebar with instructions
with st.sidebar:
    st.header("Instructions")
    st.write("""
    1. Upload your attendance Excel file
    2. View your attendance summary
    3. Select a student to see detailed analysis
    4. Check predictions for required lectures
    5. Review suggestions to improve attendance
    """)
    
    # Add information about file format
    st.header("Excel File Format")
    st.write("""
    Your Excel file should have:
    - First column: Student Names
    - Second column: PRN/Roll Numbers
    - Remaining columns: Subject-wise attendance percentages (0-100%)
    """)
    
    # Add information about the threshold
    st.info(f"The minimum attendance requirement is {MIN_ATTENDANCE_THRESHOLD}%.")
    
    # Add about section
    st.header("About")
    st.write("""
    This app helps students track their attendance and predict how many more 
    lectures they need to attend to meet the minimum attendance requirements.
    
    Version 2.0 - Improved with robust error handling and validation.
    """)

# File uploader
uploaded_file = st.file_uploader("Upload attendance Excel file", type=["xlsx", "xls"])

# Main application flow
if uploaded_file is not None:
    # Read and process the Excel file with error handling
    df, error_message = parse_excel(uploaded_file)
    
    if df is None:
        st.error(error_message)
        st.stop()
        
    # Calculate attendance with error handling
    df, attendance_cols, calc_error = calculate_attendance(df)
    
    if df is None:
        st.error(calc_error)
        st.stop()
    
    # Additional input for total conducted lectures for prediction
    st.subheader("Total Lectures Conducted So Far (For Prediction)")
    
    # Create a more compact UI with columns for input
    num_cols = max(1, min(3, len(attendance_cols)))  # Ensure at least 1 column, max 3
    cols = st.columns(num_cols)
    
    total_lectures = {}
    for i, col in enumerate(attendance_cols):
        with cols[i % num_cols]:
            # Add validation for lecture counts
            total_lectures[col] = st.number_input(
                f"{col}", 
                min_value=1, 
                max_value=1000,
                value=20, 
                key=f"total_{col}",
                help=f"Enter the total number of {col} lectures conducted so far"
            )
    
    # Display tabs for different views
    tab1, tab2 = st.tabs(["Attendance Summary", "Student Details"])
    
    with tab1:
        st.subheader("Student Attendance Summary")
        
        # Create a color-coded dataframe display with proper error handling
        try:
            # Function to highlight defaulters with color
            def highlight_defaulters(row):
                color = 'background-color: #FF5733' if row['Defaulter'] else ''
                return [color for _ in row]
            
            display_df = df[['Name', 'PRN', 'Overall_Attendance', 'Defaulter']].copy()
            display_df['Overall_Attendance'] = display_df['Overall_Attendance'].apply(lambda x: f"{x:.2f}%")
            display_df['Status'] = display_df['Defaulter'].apply(lambda x: 'Defaulter' if x else 'Regular')

            # Apply styling while 'Defaulter' column is still present
            styled_df = display_df.style.apply(highlight_defaulters, axis=1)

            # Then drop the column
            display_df = display_df.drop(columns=['Defaulter'])
            st.dataframe(styled_df, height=400)
        except Exception as e:
            st.error(f"Error displaying summary table: {str(e)}")
            st.dataframe(df[['Name', 'PRN', 'Overall_Attendance']])  # Fallback display
        
        # Summary statistics with error handling
        try:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Students", len(df))
            with col2:
                st.metric("Defaulters", df['Defaulter'].sum())
            with col3:
                st.metric("Average Attendance", f"{df['Overall_Attendance'].mean():.2f}%")
        except Exception as e:
            st.error(f"Error calculating summary statistics: {str(e)}")
        
        # Class-wise attendance visualization with error handling
        try:
            st.subheader("Subject-wise Attendance Distribution")
            avg_subject_attendance = df[attendance_cols].mean()
            
            # Limit number of subjects displayed if too many
            max_subjects_to_display = 15
            if len(attendance_cols) > max_subjects_to_display:
                st.warning(f"Displaying only the first {max_subjects_to_display} subjects due to large number of columns.")
                display_cols = attendance_cols[:max_subjects_to_display]
                avg_subject_attendance = avg_subject_attendance.iloc[:max_subjects_to_display]
            else:
                display_cols = attendance_cols
                
            fig = px.bar(
                x=display_cols,
                y=avg_subject_attendance,
                labels={'x': 'Subject', 'y': 'Average Attendance (%)'},
                color=avg_subject_attendance < MIN_ATTENDANCE_THRESHOLD,
                color_discrete_map={True: 'red', False: 'green'},
                title="Average Attendance by Subject"
            )
            # Add a horizontal line at threshold %
            fig.add_hline(y=MIN_ATTENDANCE_THRESHOLD, line_dash="dash", line_color="red", 
                        annotation_text=f"Required ({MIN_ATTENDANCE_THRESHOLD}%)")
            st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.error(f"Error creating subject attendance chart: {str(e)}")
        
        # Add a heatmap for student-subject attendance with error handling
        try:
            st.subheader("Attendance Heatmap")
            # Limit display for large datasets
            max_students_in_heatmap = 30
            max_subjects_in_heatmap = 15

            heatmap_data = df.set_index('Name')[attendance_cols]

            # If too many students, sample or limit display
            if len(heatmap_data) > max_students_in_heatmap:
                st.warning(f"Displaying only {max_students_in_heatmap} students in heatmap due to large dataset.")
                heatmap_data = heatmap_data.iloc[:max_students_in_heatmap]

            # If too many subjects, limit display
            if len(attendance_cols) > max_subjects_in_heatmap:
                st.warning(f"Displaying only {max_subjects_in_heatmap} subjects in heatmap due to large dataset.")
                heatmap_data = heatmap_data[attendance_cols[:max_subjects_in_heatmap]]
                
            fig = px.imshow(
                heatmap_data,
                labels=dict(x="Subject", y="Student", color="Attendance (%)"),
                x=heatmap_data.columns,
                y=heatmap_data.index,
                color_continuous_scale='RdYlGn',  # Red-Yellow-Green scale
                zmin=0, zmax=100,
                # Remove the width=200 parameter or set it to a larger value
                width=1000,  # Much wider value
                height=600   # Added height for better proportions
            )

            # You can also adjust the layout for better visualization
            fig.update_layout(
                margin=dict(l=50, r=50, t=30, b=50),
                xaxis_title="Subject",
                yaxis_title="Student"
            )

            # Make cells more readable
            fig.update_traces(
                textfont=dict(size=10, color="black")
            )

            st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.error(f"Error creating attendance heatmap: {str(e)}")
    
    with tab2:
        st.subheader("Student Details and Prediction")
        
        # Student selection with error handling
        try:
            selected_student = st.selectbox("Select a student to view details", df['Name'].tolist())
            
            if not selected_student:
                st.warning("Please select a student to view details.")
                st.stop()
                
            student_data = df[df['Name'] == selected_student].iloc[0]
        except Exception as e:
            st.error(f"Error selecting student data: {str(e)}")
            st.stop()
        
        # Display basic info with error handling
        try:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Name", student_data['Name'])
            with col2:
                st.metric("PRN", student_data['PRN'])
            with col3:
                status = "Defaulter" if student_data['Defaulter'] else "Regular"
                attendance_value = student_data['Overall_Attendance']
                delta_color = "off" if attendance_value < MIN_ATTENDANCE_THRESHOLD else "normal"
                st.metric("Status", status, delta=f"{attendance_value:.2f}%", delta_color=delta_color)
        except Exception as e:
            st.error(f"Error displaying student basic info: {str(e)}")
        
        # Create two columns for charts with error handling
        try:
            chart_col1, chart_col2 = st.columns(2)
            
            with chart_col1:
                # Subject-wise attendance bar chart
                subject_attendance = student_data[attendance_cols]
                
                # Limit display if too many subjects
                max_subjects_to_display = 15
                if len(attendance_cols) > max_subjects_to_display:
                    st.warning(f"Displaying only {max_subjects_to_display} subjects due to large number of columns.")
                    display_cols = attendance_cols[:max_subjects_to_display]
                    subject_attendance = subject_attendance.iloc[:max_subjects_to_display]
                else:
                    display_cols = attendance_cols
                
                bar_fig = px.bar(
                    x=display_cols,
                    y=subject_attendance,
                    title="Subject-wise Attendance",
                    color=subject_attendance < MIN_ATTENDANCE_THRESHOLD,
                    color_discrete_map={True: 'red', False: 'green'},
                    labels={'x': 'Subject', 'y': 'Attendance (%)'}
                )
                # Add a horizontal line at threshold %
                bar_fig.add_hline(y=MIN_ATTENDANCE_THRESHOLD, line_dash="dash", line_color="red", 
                                 annotation_text=f"Required ({MIN_ATTENDANCE_THRESHOLD}%)")
                st.plotly_chart(bar_fig, use_container_width=True)
            
            with chart_col2:
                # Overall attendance pie chart
                pie_fig = px.pie(
                    values=[student_data['Overall_Attendance'], MAX_ATTENDANCE_PERCENTAGE-student_data['Overall_Attendance']],
                    names=['Present', 'Absent'],
                    title="Overall Attendance Distribution",
                    color_discrete_sequence=['green', 'red']
                )
                st.plotly_chart(pie_fig, use_container_width=True)
        except Exception as e:
            st.error(f"Error creating student charts: {str(e)}")
        
        # Attendance Prediction Section with error handling
        st.subheader("Attendance Prediction")
        
        try:
            # Calculate required lectures for overall attendance with validation
            overall_total_lectures = sum(total_lectures.values()) / len(total_lectures)
            overall_required_lectures, prediction_error = predict_required_lectures(
                student_data['Overall_Attendance'], 
                overall_total_lectures
            )
            
            if prediction_error:
                st.warning(prediction_error)
            elif overall_required_lectures is not None:
                # Display overall prediction
                if overall_required_lectures > 0:
                    if overall_required_lectures == float('inf'):
                        st.warning("To achieve the target attendance, you need to attend ALL future lectures.")
                    else:
                        st.warning(f"To achieve {MIN_ATTENDANCE_THRESHOLD}% overall attendance, you need to attend at least **{overall_required_lectures}** more lectures across all subjects.")
                else:
                    st.success("Your overall attendance is already above the minimum threshold! Keep it up!")
        except Exception as e:
            st.error(f"Error calculating overall prediction: {str(e)}")
        
        # Calculate required lectures for each subject with error handling
        try:
            st.subheader("Subject-wise Prediction")
            
            # Create a more organized display with columns
            num_pred_cols = max(1, min(3, len(attendance_cols)))  # Ensure at least 1 column, max 3
            prediction_cols = st.columns(num_pred_cols)
            
            for i, subject in enumerate(attendance_cols):
                with prediction_cols[i % num_pred_cols]:
                    current_att = student_data[subject]
                    total_lect = total_lectures[subject]
                    
                    required, pred_error = predict_required_lectures(current_att, total_lect)
                    
                    if pred_error:
                        st.warning(f"{subject}: {pred_error}")
                    elif required is not None:
                        if required > 0:
                            if required == float('inf'):
                                st.metric(
                                    f"{subject}", 
                                    f"{current_att:.2f}%", 
                                    delta=f"Attend ALL future lectures",
                                    delta_color="inverse"
                                )
                            else:
                                st.metric(
                                    f"{subject}", 
                                    f"{current_att:.2f}%", 
                                    delta=f"Need {required} more lectures",
                                    delta_color="inverse"
                                )
                        else:
                            st.metric(
                                f"{subject}", 
                                f"{current_att:.2f}%", 
                                delta="On track",
                                delta_color="normal"
                            )
        except Exception as e:
            st.error(f"Error calculating subject predictions: {str(e)}")
        
        # Attendance Simulator with error handling
        try:
            st.subheader("Attendance Simulator")
            st.write("See how attending or missing future classes will affect your attendance percentage.")
            
            sim_col1, sim_col2 = st.columns(2)
            
            with sim_col1:
                num_future_classes = st.slider("Number of future classes to simulate", 1, 20, 5)
                
            with sim_col2:
                attendance_scenario = st.selectbox("Choose a scenario", [
                    "Attend all classes", 
                    "Miss all classes", 
                    "Attend some classes"
                ])
            
            attendance_rate = 0.5  # Default value
            if attendance_scenario == "Attend some classes":
                attendance_rate = st.slider("Percentage of classes to attend", 0, 100, 50) / 100
            
            # Calculate projected attendance with validation
            new_percentage, projection_data, proj_error = calculate_projected_attendance(
                student_data['Overall_Attendance'],
                overall_total_lectures,
                num_future_classes,
                attendance_scenario,
                attendance_rate
            )
            
            if proj_error:
                st.warning(proj_error)
            elif new_percentage is not None:
                # Display the result
                st.metric(
                    "Projected Attendance",
                    f"{new_percentage:.2f}%",
                    delta=f"{new_percentage - student_data['Overall_Attendance']:.2f}%",
                    delta_color="normal" if new_percentage >= MIN_ATTENDANCE_THRESHOLD else "inverse"
                )
                
                if new_percentage < MIN_ATTENDANCE_THRESHOLD:
                    st.warning(f"You would still be below the {MIN_ATTENDANCE_THRESHOLD}% threshold with this scenario.")
                elif student_data['Overall_Attendance'] < MIN_ATTENDANCE_THRESHOLD and new_percentage >= MIN_ATTENDANCE_THRESHOLD:
                    st.success(f"This scenario would bring you above the {MIN_ATTENDANCE_THRESHOLD}% threshold!")
                else:
                    st.success(f"You would maintain attendance above the {MIN_ATTENDANCE_THRESHOLD}% threshold.")
                
                # Simulate future attendance trend if we have projection data
                if projection_data:
                    st.subheader("Future Attendance Projection")
                    
                    # Unpack projection data
                    future_dates = [date for date, _ in projection_data]
                    projected_attendance = [att for _, att in projection_data]
                    
                    # Create trend chart
                    trend_fig = px.line(
                        x=future_dates, 
                        y=projected_attendance,
                        labels={'x': 'Date', 'y': 'Projected Attendance (%)'},
                        title="Future Attendance Projection"
                    )
                    trend_fig.add_hline(
                        y=MIN_ATTENDANCE_THRESHOLD, 
                        line_dash="dash", 
                        line_color="red", 
                        annotation_text=f"Minimum Required ({MIN_ATTENDANCE_THRESHOLD}%)"
                    )
                    st.plotly_chart(trend_fig, use_container_width=True)
        except Exception as e:
            st.error(f"Error in attendance simulator: {str(e)}")
        
        # Custom suggestions with error handling
        try:
            st.subheader("Custom Suggestions & Alerts")
            suggestions = generate_suggestions(student_data, attendance_cols)
            
            for suggestion in suggestions:
                st.write(suggestion)
        except Exception as e:
            st.error(f"Error generating suggestions: {str(e)}")
        
        # Attendance improvement plan with error handling
        try:
            st.subheader("Attendance Improvement Plan")
            
            if student_data['Defaulter']:
                st.error(f"⚠️ Your current attendance is below the required {MIN_ATTENDANCE_THRESHOLD}% threshold.")
                
                # Create a plan based on the predictions
                st.write("Here's a suggested plan to improve your attendance:")
                
                # Find subjects that need most attention
                subject_required_lectures = {}
                for subject in attendance_cols:
                    current_att = student_data[subject]
                    total_lect = total_lectures[subject]
                    required, _ = predict_required_lectures(current_att, total_lect)
                    
                    # Skip subjects with errors in prediction
                    if required is not None:
                        subject_required_lectures[subject] = (required, current_att)
                
                # Sort subjects by required lectures (descending)
                sorted_subjects = sorted(subject_required_lectures.items(), key=lambda x: x[1][0], reverse=True)
                
                for subject, (required, current_att) in sorted_subjects:
                    if required > 0:
                        if required == float('inf'):
                            st.write(f"- **{subject}**: Current attendance is {current_att:.2f}%. You need to attend ALL future lectures.")
                        else:
                            st.write(f"- **{subject}**: Current attendance is {current_att:.2f}%. Attend the next {required} lectures without fail.")
                    else:
                        st.write(f"- **{subject}**: Current attendance is {current_att:.2f}%. Maintain this level.")
                
                # Add some general advice
                st.info("""
                📌 **General Tips:**
                - Set reminders for classes
                - Find an accountability partner
                - Discuss with professors if you have legitimate reasons for absences
                - Keep track of your attendance weekly
                """)
            else:
                st.success("✅ Your current attendance is above the required threshold. Keep maintaining your good attendance!")
                
                # Add some general advice to maintain
                st.info("""
                📌 **Tips to Maintain Good Attendance:**
                - Continue your current attendance patterns
                - Be careful about any planned absences
                - If you need to miss a class, choose one where your attendance is highest
                """)
        except Exception as e:
            st.error(f"Error generating improvement plan: {str(e)}")

else:
    st.info("Upload an Excel file to begin tracking and predicting your attendance.")
    
    # Sample visualization for demonstration with error handling
    try:
        st.subheader("How the Prediction Works")
        
        # Create a simple demonstration
        st.write("""
        Our prediction algorithm calculates exactly how many more lectures you need to attend to reach the minimum threshold.
        
        For example, if:
        - You've attended 60 out of 100 lectures (60% attendance)
        - To reach 75% overall, you'd need to attend the next 15 lectures without missing any
        
        The formula we use is:
        
        ```
        (current_attended + x) / (total_lectures + x) = 0.75
        ```
        
        Where x is the number of consecutive lectures you need to attend.
        """)
        
        # Create a sample visualization with validation
        current_attendance = st.slider("Try it: Current Attendance Percentage", 
                                    min_value=MIN_ATTENDANCE_PERCENTAGE, 
                                    max_value=MAX_ATTENDANCE_PERCENTAGE, 
                                    value=65)
        total_lectures = st.slider("Total Lectures Conducted So Far", 10, 50, 20)
        
        required_lectures, pred_error = predict_required_lectures(current_attendance, total_lectures)
        
        if pred_error:
            st.warning(pred_error)
        elif required_lectures is not None:
            if required_lectures > 0:
                if required_lectures == float('inf'):
                    st.warning(f"With {current_attendance}% attendance after {total_lectures} lectures, you need to attend ALL future lectures to reach the threshold.")
                else:
                    st.warning(f"With {current_attendance}% attendance after {total_lectures} lectures, you need to attend **{required_lectures}** more consecutive lectures to reach the threshold.")
            else:
                st.success(f"With {current_attendance}% attendance after {total_lectures} lectures, you're already above the threshold!")
            
        # Show a simple simulation
        st.subheader("Attendance Projection Simulation")
        
        example_fig = go.Figure()
        
        # Sample projection for attending all classes
        example_attend_all = [current_attendance]
        example_miss_all = [current_attendance]
        
        # Calculate the simulation data
        total_lectures_sim = total_lectures
        current_attended_sim = (current_attendance / 100) * total_lectures_sim
        
        for i in range(1, 11):
            # Attending all future classes
            new_att_all = ((current_attended_sim + i) / (total_lectures_sim + i)) * 100
            example_attend_all.append(new_att_all)
            
            # Missing all future classes
            new_att_none = (current_attended_sim / (total_lectures_sim + i)) * 100
            example_miss_all.append(new_att_none)
        
        example_fig.add_trace(go.Scatter(
            x=list(range(11)),
            y=example_attend_all,
            mode='lines+markers',
            name='Attend All Classes'
        ))
        
        example_fig.add_trace(go.Scatter(
            x=list(range(11)),
            y=example_miss_all,
            mode='lines+markers',
            name='Miss All Classes'
        ))
        
        example_fig.add_hline(y=MIN_ATTENDANCE_THRESHOLD, 
                            line_dash="dash", 
                            line_color="red", 
                            annotation_text=f"Minimum Required ({MIN_ATTENDANCE_THRESHOLD}%)")
        
        example_fig.update_layout(
            title="Example Attendance Projection",
            xaxis_title="Number of Future Classes",
            yaxis_title="Projected Attendance (%)"
        )
        
        st.plotly_chart(example_fig, use_container_width=True)
    except Exception as e:
        st.error(f"Error in demo visualization: {str(e)}")

# Footer with helpful note
st.caption("""
**Note**: This tool provides estimates based on current attendance data. 
It assumes perfect attendance for future predictions when calculating minimum lectures needed.
For any issues or questions, please contact your academic advisor.
""")
st.markdown("\n---\nMade by Atharav K. and Samrat D.")