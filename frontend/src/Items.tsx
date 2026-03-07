import React, { useState, useEffect } from 'react';

interface Item {
    id: number;
    type: string;
    title: string;
    parent_id: number | null;
}

const Items: React.FC = () => {
    const [items, setItems] = useState<Item[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    useEffect(() => {
        const fetchItems = async () => {
            const token = localStorage.getItem('api_key');
            if (!token) return;

            try {
                const res = await fetch('/items', {
                    headers: { Authorization: `Bearer ${token}` },
                });
                if (!res.ok) throw new Error('Failed to fetch');
                const data = await res.json();
                setItems(data);
            } catch (err) {
                setError(err instanceof Error ? err.message : 'Unknown error');
            } finally {
                setLoading(false);
            }
        };

        fetchItems();
    }, []);

    if (loading) return <p>Loading items...</p>;
    if (error) return <p style={{ color: 'red' }}>Error: {error}</p>;

    return (
        <div>
            <h2>Items</h2>
            <ul>
                {items.map((item) => (
                    <li key={item.id}>
                        {item.title} ({item.type})
                    </li>
                ))}
            </ul>
        </div>
    );
};

export default Items;