import React, { useState, useEffect } from 'react';
import {
    Chart as ChartJS,
    CategoryScale,
    LinearScale,
    BarElement,
    LineElement,
    PointElement,
    Title,
    Tooltip,
    Legend,
} from 'chart.js';
import { Bar, Line } from 'react-chartjs-2';

ChartJS.register(
    CategoryScale,
    LinearScale,
    BarElement,
    LineElement,
    PointElement,
    Title,
    Tooltip,
    Legend
);

interface ScoreBucket {
    bucket: string;
    count: number;
}

interface TimelinePoint {
    date: string;
    submissions: number;
}

interface PassRateItem {
    task: string;
    avg_score: number;
    attempts: number;
}

const Dashboard: React.FC = () => {
    const [lab, setLab] = useState<string>('lab-04');
    const [scores, setScores] = useState<ScoreBucket[]>([]);
    const [timeline, setTimeline] = useState<TimelinePoint[]>([]);
    const [passRates, setPassRates] = useState<PassRateItem[]>([]);
    const [loading, setLoading] = useState<boolean>(false);
    const [error, setError] = useState<string | null>(null);

    const labs = ['lab-01', 'lab-02', 'lab-03', 'lab-04', 'lab-05'];

    const getToken = (): string | null => {
        return localStorage.getItem('api_key');
    };

    useEffect(() => {
        const fetchData = async () => {
            const token = getToken();
            if (!token) {
                setError('API key not found. Please log in.');
                return;
            }

            setLoading(true);
            setError(null);

            try {
                const [scoresRes, timelineRes, passRatesRes] = await Promise.all([
                    fetch(`/analytics/scores?lab=${lab}`, {
                        headers: { Authorization: `Bearer ${token}` },
                    }),
                    fetch(`/analytics/timeline?lab=${lab}`, {
                        headers: { Authorization: `Bearer ${token}` },
                    }),
                    fetch(`/analytics/pass-rates?lab=${lab}`, {
                        headers: { Authorization: `Bearer ${token}` },
                    }),
                ]);

                if (!scoresRes.ok || !timelineRes.ok || !passRatesRes.ok) {
                    throw new Error('Failed to fetch analytics data');
                }

                const scoresData = await scoresRes.json();
                const timelineData = await timelineRes.json();
                const passRatesData = await passRatesRes.json();

                setScores(scoresData);
                setTimeline(timelineData);
                setPassRates(passRatesData);
            } catch (err) {
                setError(err instanceof Error ? err.message : 'Unknown error');
            } finally {
                setLoading(false);
            }
        };

        fetchData();
    }, [lab]);

    const barChartData = {
        labels: scores.map((item) => item.bucket),
        datasets: [
            {
                label: 'Number of submissions',
                data: scores.map((item) => item.count),
                backgroundColor: 'rgba(75, 192, 192, 0.6)',
            },
        ],
    };

    const lineChartData = {
        labels: timeline.map((item) => item.date),
        datasets: [
            {
                label: 'Submissions per day',
                data: timeline.map((item) => item.submissions),
                borderColor: 'rgb(255, 99, 132)',
                backgroundColor: 'rgba(255, 99, 132, 0.5)',
                tension: 0.1,
            },
        ],
    };

    const chartOptions = {
        responsive: true,
        plugins: {
            legend: { position: 'top' as const },
            title: { display: false },
        },
    };

    return (
        <div style={{ padding: '20px' }}>
            <h1>Analytics Dashboard</h1>

            <div style={{ marginBottom: '20px' }}>
                <label htmlFor="lab-select">Select Lab: </label>
                <select
                    id="lab-select"
                    value={lab}
                    onChange={(e) => setLab(e.target.value)}
                    disabled={loading}
                >
                    {labs.map((l) => (
                        <option key={l} value={l}>
                            {l}
                        </option>
                    ))}
                </select>
            </div>

            {loading && <p>Loading...</p>}
            {error && <p style={{ color: 'red' }}>Error: {error}</p>}

            {!loading && !error && (
                <>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '20px' }}>
                        {scores.length > 0 && (
                            <div style={{ flex: '1 1 300px' }}>
                                <h2>Score Distribution</h2>
                                <Bar data={barChartData} options={chartOptions} />
                            </div>
                        )}
                        {timeline.length > 0 && (
                            <div style={{ flex: '1 1 300px' }}>
                                <h2>Submissions Over Time</h2>
                                <Line data={lineChartData} options={chartOptions} />
                            </div>
                        )}
                    </div>

                    {passRates.length > 0 && (
                        <div style={{ marginTop: '30px' }}>
                            <h2>Task Pass Rates</h2>
                            <table style={{ borderCollapse: 'collapse', width: '100%' }}>
                                <thead>
                                    <tr>
                                        <th style={{ border: '1px solid #ddd', padding: '8px' }}>Task</th>
                                        <th style={{ border: '1px solid #ddd', padding: '8px' }}>Avg Score</th>
                                        <th style={{ border: '1px solid #ddd', padding: '8px' }}>Attempts</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {passRates.map((item, index) => (
                                        <tr key={index}>
                                            <td style={{ border: '1px solid #ddd', padding: '8px' }}>{item.task}</td>
                                            <td style={{ border: '1px solid #ddd', padding: '8px' }}>{item.avg_score.toFixed(1)}</td>
                                            <td style={{ border: '1px solid #ddd', padding: '8px' }}>{item.attempts}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}

                    {scores.length === 0 && timeline.length === 0 && passRates.length === 0 && (
                        <p>No data available for this lab.</p>
                    )}
                </>
            )}
        </div>
    );
};

export default Dashboard;