import {useEffect, useState} from "react";
import { useLocation } from "react-router-dom";
import ErrorScreen from "./error.jsx";
function Checkout() {
    const [house_number, setHouseNumber] = useState("");
    const [postcode, setPostcode] = useState("");
    const [street, setStreet] = useState("");
    const [neighbourhood, setNeighbourhood] = useState("");
    const [city, setCity] = useState("");
    const [state, setState] = useState("");
    const [email, setEmail] = useState("");
    const [phone_number, setPhoneNumber] = useState("");
    const {stat} = useLocation();
    const [error_message, setErrorMessage] = useState("");
    const [showError, setError] = useState(false);

    useEffect(() => {
        if (stat?.order_list.length == 0) {
            setErrorMessage("An error occured"); 
            setError(true);
        }
    }, [])

    function send() {
        fetch("", {
            headers: {"Content-Type": "application/json"},
            method: "POST",
            body: JSON.stringify({
                "token": stat?.token,
                "house_number": house_number,
                "city": city,
                "state": state,
                "postcode": postcode,
                "street": street,
                "neighbourhood": neighbourhood,
                "email": email,
                "phone_number": phone_number
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data["error"]) {
                setErrorMessage(data["error"])
                setError(true);
                return;
            }
            let link = data["link"];
            window.location.href = link;
        })
        .catch(error => {
            setErrorMessage("An error occurred. Please try again.");
            setError(true);
        });
    }

    return (
        <>
        {showError && <ErrorScreen onErrorClose={setError(false)} ErrorMessage={error_message}/>}
         <div id="order">
            <div id="address_container">
               <h1>Billing information</h1>
               <div id="address">
                <div>
                    <label for="">House Number</label>
                    <br />
                    <input type="" value="" placeholder="E.g. 6" onChange={(e) => setHouseNumber(e.target.value)}/>
                    <br />

                    <label for="">Street name</label>
                    <br />
                    <input type="" value="" placeholder="E.g. Jln PU2" onChange={(e) => setStreet(e.target.value)}/>
                    <br />
                    <label for="">Postal code</label>
                    <br />
                    <input type="" value="" pattern="[1-9]\d{4}" placeholder="E.g. 47140" title="Enter a valid 5-digit Malaysian postcode" onChange={(e) => setPostcode(e.target.value)} />
                    <br />

                    <label for="">Email</label>
                    <br />
                    <input type="" value="" placeholder="E.g. ooi@outlook.com" onChange={(e) => setEmail(e.target.value)}/>
                    <br />

                    <label for="">Phone Number</label>
                    <br />
                    <input type="" value="" placeholder="E.g. 6" onChange={(e) => setPhoneNumber(e.target.value)}/>
                    <br />

                </div>
                <div>
                    <label for="">Neighbourhood</label>
                    <br />
                    <input type="" value="" placeholder="E.g. Taman Bandar Puchong" onChange={(e) => setNeighbourhood(e.target.value)} />
                    <br />
                    <label for="">City/Town</label>
                    <br />
                    <input type="" value="" placeholder="E.g. Puchong" onChange={(e) => setCity(e.target.value)} />
                    <br />
                    <label for="">State</label>
                    <br />
                    <select type="" value="" id="state" onChange={(e) => setState(e.target.value)}>
                      <option value="Selangor">Selangor</option>
                      <option value="Terrenganu">Terrenganu</option>
                    </select>
                    <br />
                </div>
               </div>
               <button class="confirm_btn" id="wide">Confirm</button>
            </div>
            
            <div id="price">
                <div id="price_details">
                    <div class="right_upper">
                        <p>Price:</p>
                        <p class="right_upper_right">RM{stat?.price}</p>
                    </div>
                    <div class="right_upper">
                        <p>Shipping fee:</p>
                        <p class="right_upper_right">RM{stat?.shipping_fee}</p>
                    </div>
                    <div class="right_upper">
                        <p class="bold_sized">Total:</p>
                        <p class="right_upper_right" id="total">RM{stat?.total}</p>
                    </div>
                </div>

                {stat?.order_list.map((item) => (
                 <div id="order_items">
                    <div>
                        <img src={item[3]} alt={item[0]} />
                        <div>
                            <p class="items_name">{item[0]}</p>
                            <p class="items_name">Qty: {String(item[1])}</p>
                        </div>
                        <p class="order_items_each_price">RM{String(item[2])}</p>
                    </div>
                 </div>
                ))}
            </div>
            <button class="confirm_btn" id="narrow" onClick={send}>Confirm</button>
        </div>
        </>
    )
}

export default Checkout;
